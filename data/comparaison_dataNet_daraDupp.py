#!/usr/bin/env python3
"""
Analyseur de duplicatas pour valider le nettoyage Confluence
Compare les fichiers dans data_clean vs duplicates en utilisant les indexations FAISS existantes
Utilise BGE-M3 avec support CUDA pour performance optimale
"""

import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
from tqdm import tqdm
from collections import defaultdict
import torch
from sentence_transformers import SentenceTransformer
import faiss
import pickle

# ===========================
# CONFIGURATION
# ===========================
CLEAN_DIR = r"D:\pfe2026\data\DC\data_clean\pages"
DUPLICATES_DIR = r"D:\pfe2026\data\DC\data_trash\duplicates\pages"
CLEAN_FAISS_DB = r"D:\pfe2026\data\DC\indexation\DocDataNetoye\faiss_db"
DUPLICATES_FAISS_DB = r"D:\pfe2026\data\DC\indexation\DocDataDuplicates\faiss_db"
OUTPUT_DIR = r"D:\pfe2026\data\DC\analysis"

MODEL_NAME = "BAAI/bge-m3"

# Fichiers générés par index_to_faiss.py
FAISS_INDEX_FILENAME = "faiss.index"
METADATA_FILENAME = "metadata.pkl"

# Seuils de similarité pour BGE-M3 (valeurs optimisées pour ce modèle)
EXACT_DUPLICATE_THRESHOLD = 0.98  # 98% = quasi identique
HIGH_SIMILARITY_THRESHOLD = 0.95  # 95% = très similaire
MEDIUM_SIMILARITY_THRESHOLD = 0.85  # 85% = possiblement similaire

# Configuration CUDA - FORCÉ
FORCE_CUDA = True  # Forcer l'utilisation de CUDA
USE_CUDA = torch.cuda.is_available()

if FORCE_CUDA and not USE_CUDA:
    raise RuntimeError(
        "❌ CUDA forcé mais non disponible!\n"
        "Solutions:\n"
        "  1. Installer PyTorch avec support CUDA: pip install torch --index-url https://download.pytorch.org/whl/cu118\n"
        "  2. Vérifier que les drivers NVIDIA sont installés\n"
        "  3. Mettre FORCE_CUDA = False dans le script pour utiliser le CPU"
    )

DEVICE = "cuda"  # Forcer cuda
BATCH_SIZE = 64  # Batch size optimisé pour GPU

# Logging
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(OUTPUT_DIR) / "duplicate_analysis.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# ===========================
# CHARGEMENT FAISS
# ===========================
class FAISSDatabase:
    """Gestionnaire de base de données FAISS."""
    
    def __init__(self, db_path: str, name: str):
        self.db_path = db_path
        self.name = name
        self.index = None
        self.metadata = None
        self.id_to_file = {}
        self.file_to_ids = defaultdict(list)
    
    def load(self):
        """Charge l'index FAISS et les métadonnées."""
        logger.info(f"\n📂 Chargement de la base {self.name}...")
        
        # Charger l'index FAISS
        index_file = Path(self.db_path) / FAISS_INDEX_FILENAME
        if not index_file.exists():
            raise FileNotFoundError(f"Index FAISS non trouvé: {index_file}")
        
        self.index = faiss.read_index(str(index_file))
        
        # FORCER le transfert vers GPU
        logger.info(f"   🚀 Transfert FORCÉ de l'index vers GPU...")
        res = faiss.StandardGpuResources()
        
        # Configuration GPU optimale
        res.setTempMemory(512 * 1024 * 1024)  # 512MB de mémoire temporaire (RTX 3050 friendly)
        
        try:
            # Transférer vers GPU avec configuration optimale
            self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
            logger.info(f"   ✅ Index sur GPU: {self.index.ntotal} vecteurs, {self.index.d} dimensions")
        except Exception as e:
            raise RuntimeError(f"❌ Impossible de transférer l'index vers GPU: {e}")
        
        # Charger les métadonnées (Pickle)
        metadata_file = Path(self.db_path) / METADATA_FILENAME
        if metadata_file.exists():
            with open(metadata_file, 'rb') as f:
                self.metadata = pickle.load(f)
            
            # Construire les mappings (List[Dict] format)
            for idx, item in enumerate(self.metadata):
                source = item.get('source_file') or item.get('source', 'unknown')
                filename = item.get('filename', os.path.basename(source))
                
                self.id_to_file[idx] = {
                    'source': source,
                    'filename': filename,
                    'chunk_index': item.get('chunk_index', 0),
                    'text': item.get('text', '') # Note: index_to_faiss doesn't save text by default
                }
                self.file_to_ids[source].append(idx)
            
            logger.info(f"   ✓ Métadonnées chargées: {len(self.file_to_ids)} fichiers uniques")
        else:
            logger.warning(f"   ⚠️  Fichier metadata non trouvé: {metadata_file}")
    
    def get_vector(self, idx: int) -> np.ndarray:
        """Récupère un vecteur par son index depuis le GPU."""
        # Pour index GPU, récupérer directement
        try:
            vector = self.index.reconstruct(int(idx))
            return vector
        except Exception as e:
            logger.error(f"Erreur récupération vecteur {idx}: {e}")
            # Fallback: essayer de transférer temporairement sur CPU
            cpu_index = faiss.index_gpu_to_cpu(self.index)
            return cpu_index.reconstruct(int(idx))
    
    def search(self, query_vector: np.ndarray, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """Recherche les k vecteurs les plus proches."""
        query_vector = np.array([query_vector], dtype=np.float32)
        distances, indices = self.index.search(query_vector, k)
        return distances[0], indices[0]


# ===========================
# ANALYSEUR DE DUPLICATAS
# ===========================
class DuplicateAnalyzer:
    """Analyseur de duplicatas utilisant les indexes FAISS."""
    
    def __init__(self):
        self.clean_db = FAISSDatabase(CLEAN_FAISS_DB, "CLEAN")
        self.duplicates_db = FAISSDatabase(DUPLICATES_FAISS_DB, "DUPLICATES")
        self.model = None
        
        # Résultats
        self.results = {
            "exact_duplicates_in_clean": [],
            "duplicates_correctly_removed": [],
            "false_positives": [],
            "borderline_cases": [],
            "statistics": {}
        }
    
    def load_databases(self):
        """Charge les deux bases de données FAISS."""
        logger.info("="*70)
        logger.info("CHARGEMENT DES BASES DE DONNÉES FAISS")
        logger.info("="*70)
        
        self.clean_db.load()
        self.duplicates_db.load()
        
        logger.info(f"\n💾 Résumé:")
        logger.info(f"   CLEAN: {len(self.clean_db.file_to_ids)} fichiers, {self.clean_db.index.ntotal} vecteurs")
        logger.info(f"   DUPLICATES: {len(self.duplicates_db.file_to_ids)} fichiers, {self.duplicates_db.index.ntotal} vecteurs")
    
    def load_model(self):
        """Charge le modèle BGE-M3 sur GPU."""
        logger.info("\n" + "="*70)
        logger.info("CHARGEMENT DU MODÈLE BGE-M3 SUR GPU")
        logger.info("="*70)
        
        # Vérifier CUDA
        logger.info(f"🔧 Configuration GPU:")
        logger.info(f"   - CUDA disponible: {torch.cuda.is_available()}")
        logger.info(f"   - Device: {DEVICE}")
        logger.info(f"   - GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"   - VRAM totale: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        logger.info(f"   - VRAM libre: {torch.cuda.memory_allocated(0) / 1e9:.2f} GB")
        
        # Charger le modèle FORCÉ sur GPU
        logger.info(f"\n📥 Chargement du modèle {MODEL_NAME}...")
        self.model = SentenceTransformer(MODEL_NAME, device="cuda")
        
        # Vérifier que le modèle est bien sur GPU
        if next(self.model.parameters()).device.type != "cuda":
            raise RuntimeError("❌ Le modèle n'est pas sur GPU!")
        
        logger.info(f"   ✅ Modèle chargé sur GPU")
        logger.info(f"   - Dimensions: {self.model.get_sentence_embedding_dimension()}")
        logger.info(f"   - Max sequence length: {self.model.max_seq_length}")
        
        # Afficher utilisation mémoire
        logger.info(f"   - VRAM utilisée: {torch.cuda.memory_allocated(0) / 1e9:.2f} GB")
    
    def analyze_internal_duplicates_in_clean(self):
        """Analyse 1: Détecter les duplicatas au sein de CLEAN."""
        logger.info("\n" + "="*70)
        logger.info("ANALYSE 1: DUPLICATAS INTERNES DANS CLEAN")
        logger.info("="*70)
        
        duplicates_found = []
        processed_pairs = set()
        
        logger.info("\n🔍 Recherche de duplicatas internes...")
        
        # Pour chaque fichier dans clean, chercher ses voisins les plus proches
        for file_path, chunk_ids in tqdm(list(self.clean_db.file_to_ids.items()), desc="Analyse clean"):
            # Prendre le premier chunk comme représentant du fichier
            if not chunk_ids:
                continue
            
            main_chunk_id = chunk_ids[0]
            query_vector = self.clean_db.get_vector(main_chunk_id)
            
            # Chercher les k plus proches voisins (k=20 pour être sûr)
            distances, indices = self.clean_db.search(query_vector, k=20)
            
            # Analyser les résultats
            for dist, idx in zip(distances, indices):
                if idx == main_chunk_id:
                    continue  # Skip le fichier lui-même
                
                similarity = dist  # IndexFlatIP returns dot product (cosine similarity)
                
                if similarity >= EXACT_DUPLICATE_THRESHOLD:
                    neighbor_info = self.clean_db.id_to_file.get(idx)
                    if neighbor_info:
                        neighbor_file = neighbor_info['source']
                        
                        # Éviter de compter la même paire deux fois
                        pair_key = tuple(sorted([file_path, neighbor_file]))
                        if pair_key not in processed_pairs and file_path != neighbor_file:
                            processed_pairs.add(pair_key)
                            
                            duplicates_found.append({
                                'file1': os.path.basename(file_path),
                                'file2': os.path.basename(neighbor_file),
                                'path1': file_path,
                                'path2': neighbor_file,
                                'similarity': float(similarity)
                            })
        
        self.results["exact_duplicates_in_clean"] = duplicates_found
        
        if duplicates_found:
            logger.warning(f"\n⚠️  PROBLÈME: {len(duplicates_found)} paires de duplicatas trouvées dans CLEAN!")
            logger.warning("Les 5 premières paires:")
            for dup in duplicates_found[:5]:
                logger.warning(f"   - {dup['file1']} ↔ {dup['file2']} (similarité: {dup['similarity']:.2%})")
        else:
            logger.info(f"\n✅ Aucun duplicata interne dans CLEAN - Excellent!")
        
        return len(duplicates_found)
    
    def analyze_duplicates_vs_clean(self):
        """Analyse 2: Vérifier si les fichiers dans DUPLICATES sont vraiment des duplicatas."""
        logger.info("\n" + "="*70)
        logger.info("ANALYSE 2: VALIDATION DES DUPLICATAS DÉTECTÉS")
        logger.info("="*70)
        
        correctly_removed = []
        false_positives = []
        borderline_cases = []
        
        logger.info("\n🔍 Comparaison DUPLICATES vs CLEAN...")
        
        for dup_file, dup_chunk_ids in tqdm(list(self.duplicates_db.file_to_ids.items()), 
                                            desc="Analyse duplicates"):
            if not dup_chunk_ids:
                continue
            
            # Prendre le premier chunk
            dup_chunk_id = dup_chunk_ids[0]
            dup_vector = self.duplicates_db.get_vector(dup_chunk_id)
            
            # Chercher dans CLEAN
            distances, indices = self.clean_db.search(dup_vector, k=5)
            
            # Analyser le meilleur match
            best_dist = distances[0]
            best_idx = indices[0]
            best_similarity = best_dist
            
            best_match_info = self.clean_db.id_to_file.get(best_idx)
            if not best_match_info:
                continue
            
            result = {
                'duplicate_file': os.path.basename(dup_file),
                'duplicate_path': dup_file,
                'best_match_clean': os.path.basename(best_match_info['source']),
                'best_match_path': best_match_info['source'],
                'similarity_score': float(best_similarity),
                'is_true_duplicate': bool(best_similarity >= HIGH_SIMILARITY_THRESHOLD)
            }
            
            # Classer selon le niveau de similarité
            if best_similarity >= EXACT_DUPLICATE_THRESHOLD:
                result['category'] = 'exact_duplicate'
                correctly_removed.append(result)
            elif best_similarity >= HIGH_SIMILARITY_THRESHOLD:
                result['category'] = 'high_similarity'
                correctly_removed.append(result)
            elif best_similarity >= MEDIUM_SIMILARITY_THRESHOLD:
                result['category'] = 'borderline'
                borderline_cases.append(result)
            else:
                result['category'] = 'false_positive'
                false_positives.append(result)
        
        self.results["duplicates_correctly_removed"] = correctly_removed
        self.results["false_positives"] = false_positives
        self.results["borderline_cases"] = borderline_cases
        
        # Afficher les résultats
        logger.info(f"\n✅ Duplicatas correctement détectés:")
        logger.info(f"   - Quasi-identiques (≥98%): {sum(1 for r in correctly_removed if r['similarity_score'] >= 0.98)}")
        logger.info(f"   - Très similaires (≥95%): {sum(1 for r in correctly_removed if 0.95 <= r['similarity_score'] < 0.98)}")
        logger.info(f"\n⚠️  Cas limites (85-95%): {len(borderline_cases)}")
        logger.info(f"⚠️  Possibles faux positifs (<85%): {len(false_positives)}")
        
        if false_positives:
            logger.warning(f"\n⚠️  Les 5 premiers faux positifs:")
            for fp in false_positives[:5]:
                logger.warning(f"   - {fp['duplicate_file']} (similarité: {fp['similarity_score']:.2%})")
                logger.warning(f"     Plus proche: {fp['best_match_clean']}")
    
    def generate_report(self):
        """Génère un rapport détaillé."""
        logger.info("\n" + "="*70)
        logger.info("GÉNÉRATION DU RAPPORT")
        logger.info("="*70)
        
        # Statistiques
        stats = {
            "total_clean_files": len(self.clean_db.file_to_ids),
            "total_duplicate_files": len(self.duplicates_db.file_to_ids),
            "internal_duplicates_in_clean": len(self.results["exact_duplicates_in_clean"]),
            "correctly_removed": len(self.results["duplicates_correctly_removed"]),
            "borderline_cases": len(self.results["borderline_cases"]),
            "false_positives": len(self.results["false_positives"]),
            "cleaning_accuracy": 0.0,
            "device_used": DEVICE,
            "model": MODEL_NAME
        }
        
        # Calculer la précision
        total_analyzed = stats["correctly_removed"] + stats["false_positives"] + stats["borderline_cases"]
        if total_analyzed > 0:
            stats["cleaning_accuracy"] = (stats["correctly_removed"] / total_analyzed) * 100
        
        self.results["statistics"] = stats
        
        # Custom encoder for numpy types
        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                                    np.int16, np.int32, np.int64, np.uint8,
                                    np.uint16, np.uint32, np.uint64)):
                    return int(obj)
                elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
                    return float(obj)
                elif isinstance(obj, (np.bool_)):
                    return bool(obj)
                elif isinstance(obj, (np.ndarray,)):
                    return obj.tolist()
                return json.JSONEncoder.default(self, obj)

        # Sauvegarder JSON
        report_file = Path(OUTPUT_DIR) / "duplicate_analysis_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
        logger.info(f"✓ Rapport JSON: {report_file}")
        
        # Rapport texte
        self._generate_readable_report()
        
        # Afficher le résumé
        logger.info("\n" + "="*70)
        logger.info("RÉSUMÉ DE L'ANALYSE")
        logger.info("="*70)
        logger.info(f"📊 Configuration:")
        logger.info(f"   - Modèle: {MODEL_NAME}")
        logger.info(f"   - Device: {DEVICE}")
        logger.info(f"   - Fichiers CLEAN: {stats['total_clean_files']}")
        logger.info(f"   - Fichiers DUPLICATES: {stats['total_duplicate_files']}")
        logger.info(f"")
        logger.info(f"🔍 Résultats:")
        logger.info(f"   - Duplicatas internes dans CLEAN: {stats['internal_duplicates_in_clean']}")
        logger.info(f"   - Duplicatas correctement détectés: {stats['correctly_removed']}")
        logger.info(f"   - Cas limites (à vérifier): {stats['borderline_cases']}")
        logger.info(f"   - Faux positifs: {stats['false_positives']}")
        logger.info(f"")
        logger.info(f"🎯 Précision du nettoyage: {stats['cleaning_accuracy']:.2f}%")
        
        # Recommandations
        self._print_recommendations(stats)
    
    def _generate_readable_report(self):
        """Génère un rapport texte."""
        report_file = Path(OUTPUT_DIR) / "duplicate_analysis_report.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("RAPPORT D'ANALYSE DES DUPLICATAS - BGE-M3\n")
            f.write("="*70 + "\n\n")
            
            stats = self.results["statistics"]
            
            # Statistiques
            f.write("STATISTIQUES GLOBALES\n")
            f.write("-"*70 + "\n")
            f.write(f"Modèle utilisé: {stats['model']}\n")
            f.write(f"Device: {stats['device_used']}\n")
            f.write(f"Fichiers CLEAN: {stats['total_clean_files']}\n")
            f.write(f"Fichiers DUPLICATES: {stats['total_duplicate_files']}\n")
            f.write(f"Précision: {stats['cleaning_accuracy']:.2f}%\n\n")
            
            # Duplicatas internes
            if self.results["exact_duplicates_in_clean"]:
                f.write("\n⚠️  DUPLICATAS INTERNES DANS CLEAN\n")
                f.write("-"*70 + "\n")
                for dup in self.results["exact_duplicates_in_clean"]:
                    f.write(f"\n{dup['file1']} ↔ {dup['file2']}\n")
                    f.write(f"  Similarité: {dup['similarity']:.2%}\n")
                    f.write(f"  Path 1: {dup['path1']}\n")
                    f.write(f"  Path 2: {dup['path2']}\n")
            
            # Faux positifs
            if self.results["false_positives"]:
                f.write("\n⚠️  FAUX POSITIFS (à récupérer)\n")
                f.write("-"*70 + "\n")
                for fp in self.results["false_positives"]:
                    f.write(f"\nFichier: {fp['duplicate_file']}\n")
                    f.write(f"  Similarité: {fp['similarity_score']:.2%}\n")
                    f.write(f"  Plus proche: {fp['best_match_clean']}\n")
                    f.write(f"  Chemin: {fp['duplicate_path']}\n")
            
            # Cas limites
            if self.results["borderline_cases"]:
                f.write("\n⚠️  CAS LIMITES (à vérifier manuellement)\n")
                f.write("-"*70 + "\n")
                for bc in self.results["borderline_cases"]:
                    f.write(f"\nFichier: {bc['duplicate_file']}\n")
                    f.write(f"  Similarité: {bc['similarity_score']:.2%}\n")
                    f.write(f"  Plus proche: {bc['best_match_clean']}\n")
        
        logger.info(f"✓ Rapport texte: {report_file}")
        
        # Liste des fichiers à récupérer
        if self.results["false_positives"]:
            fp_file = Path(OUTPUT_DIR) / "files_to_recover.txt"
            with open(fp_file, 'w', encoding='utf-8') as f:
                for fp in self.results["false_positives"]:
                    f.write(f"{fp['duplicate_path']}\n")
            logger.info(f"✓ Fichiers à récupérer: {fp_file}")
    
    def _print_recommendations(self, stats):
        """Affiche les recommandations."""
        logger.info("\n" + "="*70)
        logger.info("RECOMMANDATIONS")
        logger.info("="*70)
        
        if stats['internal_duplicates_in_clean'] > 0:
            logger.warning("❌ CRITIQUE: Duplicatas internes dans CLEAN détectés!")
            logger.warning("   → Relancer le nettoyage avec des paramètres plus stricts")
        
        if stats['false_positives'] > 0:
            logger.warning(f"⚠️  {stats['false_positives']} faux positifs détectés")
            logger.warning(f"   → Vérifier files_to_recover.txt pour les récupérer")
        
        if stats['borderline_cases'] > 10:
            logger.warning(f"⚠️  {stats['borderline_cases']} cas limites détectés")
            logger.warning("   → Vérification manuelle recommandée")
        
        if stats['cleaning_accuracy'] >= 95:
            logger.info("✅ EXCELLENT nettoyage! Vous pouvez supprimer les duplicates.")
        elif stats['cleaning_accuracy'] >= 85:
            logger.info("✅ BON nettoyage. Vérifier les cas limites avant suppression.")
        else:
            logger.warning("⚠️  Nettoyage à AMÉLIORER. Réviser les paramètres.")
    
    def run_analysis(self):
        """Exécute l'analyse complète."""
        logger.info("="*70)
        logger.info("ANALYSE DE VALIDATION DES DUPLICATAS - BGE-M3")
        logger.info("="*70)
        
        # Étape 1: Charger les bases
        self.load_databases()
        
        # Étape 2: Charger le modèle (pour référence, pas forcément utilisé)
        self.load_model()
        
        # Étape 3: Analyser duplicatas internes
        self.analyze_internal_duplicates_in_clean()
        
        # Étape 4: Analyser duplicates vs clean
        self.analyze_duplicates_vs_clean()
        
        # Étape 5: Générer rapport
        self.generate_report()
        
        logger.info("\n✅ ANALYSE TERMINÉE!")
        logger.info(f"📁 Rapports dans: {OUTPUT_DIR}")


# ===========================
# MAIN
# ===========================
def main():
    """Point d'entrée principal."""
    logger.info("="*70)
    logger.info("🚀 MODE GPU FORCÉ - ANALYSE HAUTE PERFORMANCE")
    logger.info("="*70)
    
    # Vérification CUDA obligatoire
    if not torch.cuda.is_available():
        logger.error("❌ CUDA n'est pas disponible!")
        logger.error("Veuillez installer PyTorch avec support CUDA:")
        logger.error("  pip install torch --index-url https://download.pytorch.org/whl/cu118")
        return
    
    logger.info(f"✅ CUDA détecté: {torch.cuda.get_device_name(0)}")
    logger.info(f"✅ VRAM disponible: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    
    # Vérifier FAISS GPU
    try:
        import faiss
        if not hasattr(faiss, 'StandardGpuResources'):
            logger.error("❌ FAISS-GPU n'est pas installé!")
            logger.error("Veuillez installer: pip install faiss-gpu")
            return
        logger.info("✅ FAISS-GPU détecté")
    except ImportError:
        logger.error("❌ FAISS non installé!")
        return
    
    analyzer = DuplicateAnalyzer()
    analyzer.run_analysis()


if __name__ == "__main__":
    main()