#!/usr/bin/env python3
"""
Script de nettoyage des données Confluence pour chatbot RAG
- Conserve UNE SEULE copie des duplicatas (première trouvée)
- Élimine les pages vides ou sans information utile
- Élimine les pages contenant uniquement des URLs (sauf si images)
- Préserve les fichiers avec images
- Génère des rapports d'analyse détaillés
"""

import os
import shutil
import hashlib
import re
import email
import json
from email import policy
from bs4 import BeautifulSoup
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from datetime import datetime

# ===========================
# CONFIGURATION
# ===========================
SOURCE_DIR = r"d:\pfe2026\data\confluence_complete"
CLEAN_DIR = r"d:\pfe2026\data_clean"  # Données propres pour RAG
ANALYSIS_DIR = r"d:\pfe2026\data_analysis"  # Rapports et statistiques

# Options de sauvegarde (mettre True si vous voulez garder un backup)
SAVE_TRASH = True  # False = pas de dossier trash, True = créer data_trash
TRASH_DIR = r"d:\pfe2026\data_trash"

MIN_TEXT_LENGTH = 50  # Minimum de caractères pour considérer une page utile
MIN_WORDS = 10  # Minimum de mots significatifs

# Patterns pour détecter les pages inutiles
URL_PATTERN = re.compile(r'https?://[^\s]+', re.IGNORECASE)
USELESS_PATTERNS = [
    r'^bienvenue\s*!?\s*$',
    r'^welcome\s*!?\s*$',
    r'^accueil\s*$',
    r'^home\s*$',
]

# Setup logging
LOG_FILE = Path(ANALYSIS_DIR) / f'nettoyage_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
os.makedirs(ANALYSIS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def get_text_content(file_path: str) -> Optional[Tuple[str, bool]]:
    """
    Extrait le contenu textuel d'un fichier .doc (MHTML format).
    Retourne (texte_normalisé, contains_images) ou None si l'extraction échoue.
    """
    try:
        with open(file_path, 'rb') as f:
            content_bytes = f.read()

        # Essayer de parser comme email (format MHTML)
        msg = email.message_from_bytes(content_bytes, policy=policy.default)
        html_content = None
        has_images = False

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/html':
                    html_content = part.get_content()
                elif content_type.startswith('image/'):
                    has_images = True
        else:
            if msg.get_content_type() == 'text/html':
                html_content = msg.get_content()

        if not html_content:
            html_content = content_bytes.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_content, 'html.parser')
        
        if not has_images:
            img_tags = soup.find_all('img')
            if img_tags:
                has_images = True
            if not has_images and ('data:image/' in html_content or 'base64' in html_content.lower()):
                has_images = True
        
        for element in soup(['script', 'style', 'meta', 'link', 'noscript']):
            element.decompose()

        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())
        
        return (text, has_images)

    except Exception as e:
        logger.error(f"Erreur lors de la lecture de {file_path}: {e}")
        return None


def is_url_only(text: str) -> bool:
    """Vérifie si le texte contient uniquement des URLs (>80%)."""
    if not text:
        return False
    
    urls = URL_PATTERN.findall(text)
    if not urls:
        return False
    
    url_length = sum(len(url) for url in urls)
    text_length = len(text)
    url_ratio = url_length / text_length if text_length > 0 else 0
    
    return url_ratio > 0.8


def is_useless_content(text: str, has_images: bool = False) -> Tuple[bool, str]:
    """
    Vérifie si le contenu est inutile.
    Les fichiers avec images ne sont JAMAIS considérés comme inutiles.
    """
    if not text:
        if has_images:
            return False, ""
        return True, "Contenu vide"
    
    if has_images:
        return False, ""
    
    if len(text) < MIN_TEXT_LENGTH:
        return True, f"Trop court ({len(text)} chars)"
    
    words = [w for w in text.split() if len(w) > 2]
    if len(words) < MIN_WORDS:
        return True, f"Pas assez de mots ({len(words)} mots)"
    
    text_lower = text.lower().strip()
    for pattern in USELESS_PATTERNS:
        if re.match(pattern, text_lower):
            return True, f"Pattern inutile: {pattern}"
    
    return False, ""


def compute_content_hash(text: str) -> str:
    """Calcule le hash SHA256 du contenu normalisé."""
    normalized = ' '.join(text.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def format_size(size_bytes: int) -> str:
    """Formate la taille en octets."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def get_directory_size(directory: str) -> int:
    """Calcule la taille totale d'un répertoire."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def ensure_directory_structure(source_path: str, base_source: str, base_dest: str) -> str:
    """Crée la structure de dossiers dans la destination."""
    relative_path = os.path.relpath(os.path.dirname(source_path), base_source)
    dest_dir = os.path.join(base_dest, relative_path)
    os.makedirs(dest_dir, exist_ok=True)
    return dest_dir


def save_analysis_report(stats: Dict, duplicates_info: Dict, removed_files: Dict):
    """Sauvegarde les rapports d'analyse en JSON et TXT."""
    
    # Rapport principal JSON
    report = {
        "date": datetime.now().isoformat(),
        "source_dir": SOURCE_DIR,
        "clean_dir": CLEAN_DIR,
        "statistics": stats,
        "configuration": {
            "min_text_length": MIN_TEXT_LENGTH,
            "min_words": MIN_WORDS,
            "save_trash": SAVE_TRASH
        }
    }
    
    report_file = Path(ANALYSIS_DIR) / 'rapport_nettoyage.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Mapping des duplicatas
    duplicates_file = Path(ANALYSIS_DIR) / 'duplicates_map.json'
    with open(duplicates_file, 'w', encoding='utf-8') as f:
        json.dump(duplicates_info, f, indent=2, ensure_ascii=False)
    
    # Liste des fichiers exclus
    removed_file = Path(ANALYSIS_DIR) / 'removed_files.txt'
    with open(removed_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("FICHIERS EXCLUS DU DATASET RAG\n")
        f.write("=" * 80 + "\n\n")
        
        if removed_files['duplicates']:
            f.write(f"\n🔄 DUPLICATAS ({len(removed_files['duplicates'])} fichiers)\n")
            f.write("-" * 80 + "\n")
            for dup in removed_files['duplicates']:
                f.write(f"  ❌ {dup['file']}\n")
                f.write(f"     → Duplicata de: {dup['original']}\n\n")
        
        if removed_files['useless']:
            f.write(f"\n⛔ CONTENU INUTILE ({len(removed_files['useless'])} fichiers)\n")
            f.write("-" * 80 + "\n")
            for item in removed_files['useless']:
                f.write(f"  ❌ {item['file']}\n")
                f.write(f"     → Raison: {item['reason']}\n\n")
        
        if removed_files['url_only']:
            f.write(f"\n🔗 URL-ONLY ({len(removed_files['url_only'])} fichiers)\n")
            f.write("-" * 80 + "\n")
            for item in removed_files['url_only']:
                f.write(f"  ❌ {item}\n")
        
        if removed_files['errors']:
            f.write(f"\n❌ ERREURS ({len(removed_files['errors'])} fichiers)\n")
            f.write("-" * 80 + "\n")
            for item in removed_files['errors']:
                f.write(f"  ❌ {item}\n")
    
    logger.info(f"📊 Rapports sauvegardés dans: {ANALYSIS_DIR}")


def main():
    """Fonction principale de nettoyage optimisée pour RAG."""
    logger.info("=" * 80)
    logger.info("NETTOYAGE DES DONNÉES CONFLUENCE POUR CHATBOT RAG")
    logger.info("=" * 80)
    logger.info(f"📂 Source: {SOURCE_DIR}")
    logger.info(f"✨ Destination (données propres): {CLEAN_DIR}")
    logger.info(f"📊 Rapports d'analyse: {ANALYSIS_DIR}")
    if SAVE_TRASH:
        logger.info(f"🗑️  Backup des fichiers exclus: {TRASH_DIR}")
    logger.info(f"\n⚙️  Critères:")
    logger.info(f"   - Longueur minimale: {MIN_TEXT_LENGTH} caractères")
    logger.info(f"   - Mots minimaux: {MIN_WORDS} mots")
    logger.info(f"   - URL-only: >80% du contenu (sauf si images)")
    logger.info(f"   - Fichiers avec images: TOUJOURS conservés")
    logger.info(f"   - Duplicatas: PREMIÈRE copie conservée uniquement")
    logger.info("=" * 80)

    if not os.path.exists(SOURCE_DIR):
        logger.error(f"Le répertoire source n'existe pas: {SOURCE_DIR}")
        return

    # Créer les répertoires
    os.makedirs(CLEAN_DIR, exist_ok=True)
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    
    # Créer trash si demandé
    if SAVE_TRASH:
        os.makedirs(TRASH_DIR, exist_ok=True)
        trash_dirs = {
            'duplicates': os.path.join(TRASH_DIR, "duplicates"),
            'useless': os.path.join(TRASH_DIR, "useless"),
            'url_only': os.path.join(TRASH_DIR, "url_only"),
            'errors': os.path.join(TRASH_DIR, "errors")
        }
        for d in trash_dirs.values():
            os.makedirs(d, exist_ok=True)

    # Statistiques
    stats = {
        'processed': 0,
        'kept': 0,
        'kept_with_images': 0,
        'skipped_duplicate': 0,
        'skipped_useless': 0,
        'skipped_url_only': 0,
        'skipped_error': 0,
        'non_doc_copied': 0
    }
    
    # Tracking pour rapports
    seen_hashes = {}  # hash -> (file_path, file_name)
    duplicates_info = {}  # original -> [duplicates]
    removed_files = {
        'duplicates': [],
        'useless': [],
        'url_only': [],
        'errors': []
    }
    
    logger.info("\n🚀 Début du traitement des fichiers...\n")
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            stats['processed'] += 1
            source_file = os.path.join(root, file)
            relative_file = os.path.relpath(source_file, SOURCE_DIR)
            
            if file.lower().endswith('.doc'):
                result = get_text_content(source_file)
                
                if result is None:
                    if SAVE_TRASH:
                        dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, trash_dirs['errors'])
                        shutil.copy2(source_file, os.path.join(dest_dir, file))
                    removed_files['errors'].append(relative_file)
                    logger.warning(f"❌ Erreur d'extraction: {relative_file}")
                    stats['skipped_error'] += 1
                    continue
                
                text, has_images = result

                # 1. Vérifier si inutile
                is_useless, reason = is_useless_content(text, has_images)
                if is_useless:
                    if SAVE_TRASH:
                        dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, trash_dirs['useless'])
                        shutil.copy2(source_file, os.path.join(dest_dir, file))
                    removed_files['useless'].append({'file': relative_file, 'reason': reason})
                    logger.info(f"⛔ Inutile ({reason}): {relative_file}")
                    stats['skipped_useless'] += 1
                    continue

                # 2. Vérifier URL-only (sauf si images)
                if is_url_only(text) and not has_images:
                    if SAVE_TRASH:
                        dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, trash_dirs['url_only'])
                        shutil.copy2(source_file, os.path.join(dest_dir, file))
                    removed_files['url_only'].append(relative_file)
                    logger.info(f"🔗 URL-only: {relative_file}")
                    stats['skipped_url_only'] += 1
                    continue

                # 3. Vérifier duplicatas - CONSERVER LA PREMIÈRE copie
                content_hash = compute_content_hash(text)
                if content_hash in seen_hashes:
                    original_file, original_name = seen_hashes[content_hash]
                    original_relative = os.path.relpath(original_file, SOURCE_DIR)
                    
                    if SAVE_TRASH:
                        dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, trash_dirs['duplicates'])
                        shutil.copy2(source_file, os.path.join(dest_dir, file))
                    
                    # Tracking
                    if original_relative not in duplicates_info:
                        duplicates_info[original_relative] = []
                    duplicates_info[original_relative].append(relative_file)
                    
                    removed_files['duplicates'].append({
                        'file': relative_file,
                        'original': original_relative
                    })
                    
                    logger.info(f"🔄 Duplicata de '{original_name}': {relative_file}")
                    stats['skipped_duplicate'] += 1
                    continue
                
                # Enregistrer comme original (PREMIÈRE occurrence)
                seen_hashes[content_hash] = (source_file, file)
                
                # Copier vers CLEAN_DIR
                dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, CLEAN_DIR)
                dest_file = os.path.join(dest_dir, file)
                shutil.copy2(source_file, dest_file)
                
                if has_images:
                    stats['kept_with_images'] += 1
                    logger.info(f"✅ Conservé ({len(text)} chars, 🖼️ images): {relative_file}")
                else:
                    logger.info(f"✅ Conservé ({len(text)} chars): {relative_file}")
                stats['kept'] += 1
            
            else:
                # Copier les fichiers non-.doc
                dest_dir = ensure_directory_structure(source_file, SOURCE_DIR, CLEAN_DIR)
                dest_file = os.path.join(dest_dir, file)
                shutil.copy2(source_file, dest_file)
                stats['non_doc_copied'] += 1

    # Calculer les tailles
    source_size = get_directory_size(SOURCE_DIR)
    clean_size = get_directory_size(CLEAN_DIR)
    
    # Sauvegarder les rapports
    save_analysis_report(stats, duplicates_info, removed_files)
    
    # Afficher le résumé
    logger.info("\n" + "=" * 80)
    logger.info("✨ NETTOYAGE TERMINÉ - DONNÉES PRÊTES POUR RAG")
    logger.info("=" * 80)
    logger.info(f"📊 Fichiers traités: {stats['processed']}")
    logger.info(f"   ✅ Fichiers .doc conservés: {stats['kept']}")
    logger.info(f"      └─ Dont avec images: {stats['kept_with_images']}")
    logger.info(f"   📄 Fichiers non-.doc copiés: {stats['non_doc_copied']}")
    logger.info(f"   🔄 Duplicatas exclus: {stats['skipped_duplicate']}")
    logger.info(f"   ⛔ Contenu inutile exclu: {stats['skipped_useless']}")
    logger.info(f"   🔗 URL-only exclu: {stats['skipped_url_only']}")
    logger.info(f"   ❌ Erreurs: {stats['skipped_error']}")
    logger.info("-" * 80)
    logger.info(f"💾 Taille SOURCE: {format_size(source_size)}")
    logger.info(f"✨ Taille CLEAN (RAG): {format_size(clean_size)}")
    logger.info(f"🎯 Réduction: {format_size(source_size - clean_size)} ({100 - (clean_size/source_size*100):.1f}%)")
    logger.info("=" * 80)
    logger.info(f"\n📁 Dossiers générés:")
    logger.info(f"   ✨ Données propres pour RAG: {CLEAN_DIR}")
    logger.info(f"   📊 Rapports d'analyse: {ANALYSIS_DIR}")
    if SAVE_TRASH:
        logger.info(f"   🗑️  Backup (trash): {TRASH_DIR}")
    logger.info(f"\n📋 Fichiers de rapport:")
    logger.info(f"   - rapport_nettoyage.json (statistiques complètes)")
    logger.info(f"   - duplicates_map.json (mapping des duplicatas)")
    logger.info(f"   - removed_files.txt (fichiers exclus détaillés)")
    logger.info(f"   - {LOG_FILE.name} (log complet)")
    logger.info("\n🤖 Vos données sont prêtes pour l'indexation RAG!")


if __name__ == "__main__":
    main()