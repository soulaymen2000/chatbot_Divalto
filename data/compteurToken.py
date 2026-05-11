#!/usr/bin/env python3
"""
Compteur de tokens pour fichiers texte
✔ Compte les tokens avec tiktoken (GPT tokenizer)
✔ Génère 2 fichiers log triés par ordre croissant
✔ Support fichiers .txt et .doc
✔ Statistiques détaillées
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import logging
from tqdm import tqdm
from datetime import datetime
import tiktoken
import email
from email import policy
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
# Dossiers à analyser
FOLDERS = [
    Path(r"D:\pfe2026\data\DC\donnerCodage\CHM_EXTRACTED\text"),
    Path(r"D:\pfe2026\data\DC\donneFonctionnel\data_clean\pages")
]

# Dossier de sortie pour les logs
OUTPUT_DIR = Path(r"D:\pfe2026\logs\token_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Nom des fichiers de sortie
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_CHM = OUTPUT_DIR / f"tokens_chm_{TIMESTAMP}.log"
LOG_PAGES = OUTPUT_DIR / f"tokens_pages_{TIMESTAMP}.log"

# Tokenizer (GPT-3.5/4 compatible)
ENCODING_NAME = "cl100k_base"  # Utilisé par GPT-3.5 et GPT-4

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / f"token_count_{TIMESTAMP}.log", 
                          mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# =========================
# EXTRACTION TEXTE
# =========================
def extract_text_from_txt(path: Path) -> str:
    """Lit un fichier .txt avec gestion d'encodage"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Erreur lecture {path.name}: {e}")
            return ""
    except Exception as e:
        logger.warning(f"Erreur lecture {path.name}: {e}")
        return ""

def extract_text_from_doc(path: Path) -> str:
    """Extrait le texte d'un fichier .doc (MHTML)"""
    try:
        with open(path, 'rb') as f:
            content_bytes = f.read()

        # Parser comme email MHTML
        msg = email.message_from_bytes(content_bytes, policy=policy.default)
        html_content = None

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    html_content = part.get_content()
                    break
        else:
            if msg.get_content_type() == 'text/html':
                html_content = msg.get_content()

        if not html_content:
            html_content = content_bytes.decode('utf-8', errors='ignore')

        # Parser HTML avec BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Supprimer les éléments non-textuels
        for element in soup(['script', 'style', 'meta', 'link', 'noscript']):
            element.decompose()

        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())
        
        return text

    except Exception as e:
        logger.warning(f"Erreur extraction {path.name}: {e}")
        return ""

def extract_text(path: Path) -> str:
    """Route vers la bonne fonction d'extraction selon l'extension"""
    ext = path.suffix.lower()
    if ext == '.txt':
        return extract_text_from_txt(path)
    elif ext == '.doc':
        return extract_text_from_doc(path)
    else:
        logger.warning(f"Extension non supportée: {ext}")
        return ""

# =========================
# COMPTAGE TOKENS
# =========================
def count_tokens(text: str, encoding) -> int:
    """Compte le nombre de tokens dans un texte"""
    try:
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        logger.warning(f"Erreur comptage tokens: {e}")
        return 0

def analyze_folder(folder: Path, encoding) -> List[Dict]:
    """
    Analyse tous les fichiers d'un dossier et retourne les stats
    
    Returns:
        Liste de dictionnaires avec: path, filename, tokens, size, relative_path
    """
    results = []
    
    # Trouver tous les fichiers .txt et .doc
    txt_files = list(folder.rglob("*.txt"))
    doc_files = list(folder.rglob("*.doc"))
    all_files = txt_files + doc_files
    
    logger.info(f"📂 Analyse de {folder}")
    logger.info(f"   Trouvé {len(txt_files)} fichiers .txt et {len(doc_files)} fichiers .doc")
    
    if not all_files:
        logger.warning(f"   ⚠️ Aucun fichier trouvé dans {folder}")
        return results
    
    for file_path in tqdm(all_files, desc=f"Analyse {folder.name}"):
        # Extraire le texte
        text = extract_text(file_path)
        
        if not text:
            continue
        
        # Compter les tokens
        token_count = count_tokens(text, encoding)
        
        # Taille du fichier
        file_size = file_path.stat().st_size
        
        # Chemin relatif
        relative_path = file_path.relative_to(folder)
        
        results.append({
            'path': str(file_path),
            'relative_path': str(relative_path),
            'filename': file_path.name,
            'tokens': token_count,
            'size_bytes': file_size,
            'size_kb': file_size / 1024,
            'extension': file_path.suffix.lower()
        })
    
    logger.info(f"   ✅ {len(results)} fichiers analysés")
    return results

# =========================
# GÉNÉRATION DES LOGS
# =========================
def generate_log_file(results: List[Dict], output_file: Path, folder_name: str):
    """
    Génère un fichier log trié par ordre croissant de tokens
    """
    if not results:
        logger.warning(f"Aucun résultat pour {folder_name}")
        return
    
    # Trier par nombre de tokens (ordre croissant)
    sorted_results = sorted(results, key=lambda x: x['tokens'])
    
    # Calculer les statistiques
    total_tokens = sum(r['tokens'] for r in results)
    total_size_mb = sum(r['size_bytes'] for r in results) / (1024 * 1024)
    avg_tokens = total_tokens / len(results) if results else 0
    min_tokens = sorted_results[0]['tokens'] if sorted_results else 0
    max_tokens = sorted_results[-1]['tokens'] if sorted_results else 0
    
    # Écrire le fichier log
    with open(output_file, 'w', encoding='utf-8') as f:
        # En-tête
        f.write("=" * 100 + "\n")
        f.write(f"ANALYSE DES TOKENS - {folder_name}\n")
        f.write("=" * 100 + "\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Dossier source: {FOLDERS[0] if 'chm' in folder_name.lower() else FOLDERS[1]}\n")
        f.write(f"Encodage: {ENCODING_NAME}\n")
        f.write("\n")
        
        # Statistiques globales
        f.write("STATISTIQUES GLOBALES\n")
        f.write("-" * 100 + "\n")
        f.write(f"Nombre de fichiers:    {len(results):,}\n")
        f.write(f"Total tokens:          {total_tokens:,}\n")
        f.write(f"Taille totale:         {total_size_mb:.2f} MB\n")
        f.write(f"Moyenne tokens/fichier: {avg_tokens:,.0f}\n")
        f.write(f"Minimum tokens:        {min_tokens:,}\n")
        f.write(f"Maximum tokens:        {max_tokens:,}\n")
        f.write("\n")
        
        # Distribution par quantiles
        f.write("DISTRIBUTION\n")
        f.write("-" * 100 + "\n")
        percentiles = [10, 25, 50, 75, 90, 95, 99]
        for p in percentiles:
            idx = int(len(sorted_results) * p / 100)
            if idx < len(sorted_results):
                f.write(f"P{p:2d}:  {sorted_results[idx]['tokens']:,} tokens\n")
        f.write("\n")
        
        # Liste détaillée (ordre croissant)
        f.write("DÉTAILS PAR FICHIER (ordre croissant de tokens)\n")
        f.write("-" * 100 + "\n")
        f.write(f"{'#':<6} {'Tokens':<12} {'Taille (KB)':<12} {'Type':<6} {'Chemin relatif'}\n")
        f.write("-" * 100 + "\n")
        
        for i, result in enumerate(sorted_results, 1):
            f.write(f"{i:<6} {result['tokens']:<12,} {result['size_kb']:<12.2f} "
                   f"{result['extension']:<6} {result['relative_path']}\n")
        
        f.write("\n")
        f.write("=" * 100 + "\n")
        f.write("FIN DU RAPPORT\n")
        f.write("=" * 100 + "\n")
    
    logger.info(f"✅ Log généré: {output_file}")
    logger.info(f"   Total: {total_tokens:,} tokens dans {len(results)} fichiers")

# =========================
# FONCTION PRINCIPALE
# =========================
def main():
    logger.info("=" * 100)
    logger.info("ANALYSE DES TOKENS DANS LES FICHIERS")
    logger.info("=" * 100)
    logger.info(f"Encodage: {ENCODING_NAME}")
    logger.info(f"Dossiers à analyser: {len(FOLDERS)}")
    for folder in FOLDERS:
        logger.info(f"   • {folder}")
    logger.info("=" * 100)
    
    # Vérifier que les dossiers existent
    for folder in FOLDERS:
        if not folder.exists():
            logger.error(f"❌ Dossier introuvable: {folder}")
            sys.exit(1)
    
    # Charger le tokenizer
    logger.info("\n📝 Chargement du tokenizer...")
    try:
        encoding = tiktoken.get_encoding(ENCODING_NAME)
        logger.info(f"   ✅ Tokenizer chargé: {ENCODING_NAME}")
    except Exception as e:
        logger.error(f"❌ Erreur chargement tokenizer: {e}")
        sys.exit(1)
    
    # Analyser chaque dossier
    all_results = []
    
    # 1️⃣ Dossier CHM
    logger.info("\n" + "=" * 100)
    logger.info("1️⃣ ANALYSE DU DOSSIER CHM")
    logger.info("=" * 100)
    results_chm = analyze_folder(FOLDERS[0], encoding)
    all_results.append(('CHM', results_chm, LOG_CHM))
    
    # 2️⃣ Dossier Pages
    logger.info("\n" + "=" * 100)
    logger.info("2️⃣ ANALYSE DU DOSSIER PAGES")
    logger.info("=" * 100)
    results_pages = analyze_folder(FOLDERS[1], encoding)
    all_results.append(('Pages', results_pages, LOG_PAGES))
    
    # Générer les logs
    logger.info("\n" + "=" * 100)
    logger.info("📊 GÉNÉRATION DES FICHIERS LOG")
    logger.info("=" * 100)
    
    for name, results, log_file in all_results:
        generate_log_file(results, log_file, name)
    
    # Statistiques finales
    logger.info("\n" + "=" * 100)
    logger.info("✅ ANALYSE TERMINÉE")
    logger.info("=" * 100)
    
    for name, results, log_file in all_results:
        if results:
            total = sum(r['tokens'] for r in results)
            logger.info(f"\n📁 {name}:")
            logger.info(f"   Fichiers: {len(results)}")
            logger.info(f"   Tokens: {total:,}")
            logger.info(f"   Log: {log_file}")
    
    logger.info("\n" + "=" * 100)
    logger.info(f"📂 Tous les logs sont dans: {OUTPUT_DIR}")
    logger.info("=" * 100)


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    main()