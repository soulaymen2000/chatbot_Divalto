#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extraction FINALE des tableaux - ENCODAGE FIXÉ
✔ Support complet caractères spéciaux (accents, €, ®, ™, etc.)
✔ Nettoyage HTML entities (&nbsp;, &eacute;, etc.)
✔ Détection automatique encodage
✔ CSV UTF-8 avec BOM pour Excel
✔ Hiérarchie préservée
"""

import csv
import email
from email import policy
from pathlib import Path
from bs4 import BeautifulSoup
import chardet
import logging
import html
import unicodedata
import re

# =========================
# CONFIG
# =========================
INPUT_DIR = Path(r"D:\pfe2026\data\DC\data_clean\pages")
OUTPUT_DIR = Path(r"D:\pfe2026\data\DC\tables_csv")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# LOGGING
# =========================
LOG_FILE = OUTPUT_DIR / "extraction_tables.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# =========================
# NETTOYAGE TEXTE AVANCÉ
# =========================
def clean_text_advanced(text: str) -> str:
    """
    Nettoyage avancé avec gestion complète des caractères spéciaux.
    """
    if not text:
        return ""
    
    # 1. Décoder les HTML entities (&eacute; → é, &nbsp; → espace, etc.)
    text = html.unescape(text)
    
    # 2. Normaliser les caractères Unicode (NFKC = compatibilité maximale)
    text = unicodedata.normalize('NFKC', text)
    
    # 3. Remplacer les espaces spéciaux
    replacements = {
        '\xa0': ' ',      # Non-breaking space
        '\u200b': '',     # Zero-width space
        '\u200c': '',     # Zero-width non-joiner
        '\u200d': '',     # Zero-width joiner
        '\ufeff': '',     # Zero-width no-break space (BOM)
        '\u2009': ' ',    # Thin space
        '\u202f': ' ',    # Narrow no-break space
        '\u00a0': ' ',    # Non-breaking space (autre forme)
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # 4. Normaliser les retours à la ligne
    text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    
    # 5. Réduire les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    
    # 6. Strip et retourner
    return text.strip()

# =========================
# EXTRACTION HTML AVEC ENCODAGE ROBUSTE
# =========================
def extract_html_content(doc_path: Path) -> str:
    """
    Extrait le contenu HTML avec détection automatique d'encodage.
    """
    try:
        raw_bytes = doc_path.read_bytes()
    except Exception as e:
        logger.error(f"❌ Impossible de lire {doc_path.name}: {e}")
        return ""
    
    html_content = None
    
    # Méthode 1: Parser comme MHTML
    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
        
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        # Essayer d'obtenir le contenu en UTF-8
                        html_content = part.get_content()
                        break
                    except:
                        # Fallback: décoder manuellement
                        payload = part.get_payload(decode=True)
                        if payload:
                            html_content = payload.decode('utf-8', errors='ignore')
                            break
        else:
            if msg.get_content_type() == "text/html":
                try:
                    html_content = msg.get_content()
                except:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        html_content = payload.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f"⚠️ Parsing MHTML échoué pour {doc_path.name}: {e}")
    
    # Méthode 2: Détection automatique d'encodage
    if not html_content:
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding", "utf-8")
        confidence = detected.get("confidence", 0)
        
        logger.debug(f"Encodage détecté: {encoding} (confiance: {confidence:.2%})")
        
        # Essayer l'encodage détecté
        try:
            html_content = raw_bytes.decode(encoding, errors='replace')
        except:
            # Fallback ultime: UTF-8 avec remplacement
            html_content = raw_bytes.decode('utf-8', errors='replace')
    
    return html_content

# =========================
# EXTRACTION TABLEAUX
# =========================
def extract_valid_tables(doc_path: Path):
    """
    Extrait les tableaux valides avec nettoyage avancé.
    """
    html_content = extract_html_content(doc_path)
    
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, "html.parser")
    valid_tables = []
    
    for table in soup.find_all("table"):
        rows = []
        col_counts = set()
        has_header = False
        
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            
            # Extraire et nettoyer chaque cellule
            row = []
            for cell in cells:
                # Obtenir le texte brut
                cell_text = cell.get_text(" ", strip=True)
                # Nettoyer avec fonction avancée
                cleaned = clean_text_advanced(cell_text)
                row.append(cleaned)
            
            # Ignorer lignes complètement vides
            if not any(row):
                continue
            
            rows.append(row)
            col_counts.add(len(row))
            
            # Détecter header
            if tr.find("th"):
                has_header = True
        
        # Filtrage intelligent
        if (
            len(rows) >= 2 and              # Au moins 2 lignes
            max(col_counts) >= 2 and        # Au moins 2 colonnes
            (has_header or len(col_counts) == 1)  # Header OU structure uniforme
        ):
            valid_tables.append(rows)
    
    return valid_tables

# =========================
# SAUVEGARDE CSV AVEC UTF-8 BOM
# =========================
def save_tables_csv(doc_path: Path, tables):
    """
    Sauvegarde les tableaux en CSV UTF-8 avec BOM pour Excel.
    """
    relative_path = doc_path.relative_to(INPUT_DIR)
    output_dir = OUTPUT_DIR / relative_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    base_name = doc_path.stem
    
    for idx, table in enumerate(tables, start=1):
        csv_path = output_dir / f"{base_name}_table_{idx}.csv"
        
        try:
            # Écrire avec UTF-8 BOM pour compatibilité Excel
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(
                    f,
                    delimiter=";",
                    quoting=csv.QUOTE_MINIMAL,
                    quotechar='"',
                    escapechar='\\'
                )
                
                for row in table:
                    writer.writerow(row)
            
            logger.debug(f"   ✅ {csv_path.name}")
        
        except Exception as e:
            logger.error(f"   ❌ Erreur sauvegarde {csv_path.name}: {e}")

# =========================
# VALIDATION CSV
# =========================
def validate_csv(csv_path: Path) -> bool:
    """
    Vérifie qu'un CSV est bien formé et lisible.
    """
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=';')
            rows = list(reader)
            return len(rows) > 0
    except Exception as e:
        logger.error(f"⚠️ CSV invalide {csv_path.name}: {e}")
        return False

# =========================
# MAIN
# =========================
def main():
    logger.info("="*70)
    logger.info("🚀 EXTRACTION TABLEAUX - ENCODAGE FIXÉ")
    logger.info("="*70)
    logger.info(f"📂 Source: {INPUT_DIR}")
    logger.info(f"📁 Destination: {OUTPUT_DIR}")
    logger.info("="*70)
    
    files = list(INPUT_DIR.rglob("*.doc"))
    logger.info(f"\n📂 {len(files)} fichiers .doc trouvés\n")
    
    stats = {
        "total_files": len(files),
        "files_with_tables": 0,
        "total_tables": 0,
        "failed_files": 0
    }
    
    for i, doc_file in enumerate(files, 1):
        logger.info(f"📄 [{i}/{len(files)}] {doc_file.relative_to(INPUT_DIR)}")
        
        try:
            tables = extract_valid_tables(doc_file)
            
            if tables:
                save_tables_csv(doc_file, tables)
                stats["files_with_tables"] += 1
                stats["total_tables"] += len(tables)
                logger.info(f"   ✅ {len(tables)} tableaux extraits")
            else:
                logger.debug(f"   ⚪ Aucun tableau valide")
        
        except Exception as e:
            stats["failed_files"] += 1
            logger.error(f"   ❌ Erreur: {e}")
    
    # Résumé
    logger.info("\n" + "="*70)
    logger.info("✅ EXTRACTION TERMINÉE")
    logger.info("="*70)
    logger.info(f"📊 Statistiques:")
    logger.info(f"   • Fichiers traités: {stats['total_files']}")
    logger.info(f"   • Fichiers avec tableaux: {stats['files_with_tables']}")
    logger.info(f"   • Total tableaux: {stats['total_tables']}")
    logger.info(f"   • Erreurs: {stats['failed_files']}")
    logger.info(f"\n📁 Résultat: {OUTPUT_DIR}")
    logger.info(f"📝 Log: {LOG_FILE}")
    logger.info("="*70)
    
    # Validation d'échantillons
    csv_files = list(OUTPUT_DIR.rglob("*.csv"))
    if csv_files:
        logger.info(f"\n🔍 Validation de 5 CSV aléatoires...")
        import random
        samples = random.sample(csv_files, min(5, len(csv_files)))
        for csv_file in samples:
            valid = validate_csv(csv_file)
            status = "✅" if valid else "❌"
            logger.info(f"   {status} {csv_file.name}")

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    main()