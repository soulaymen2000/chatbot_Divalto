#!/usr/bin/env python3
"""
Extraction des images depuis fichiers .doc (MHTML Confluence)
✔ Support application/octet-stream (images déguisées)
✔ Détection magic bytes pour identification
✔ Hiérarchie préservée
"""

import email
from email import policy
from pathlib import Path
import json
import logging
import re
import base64
from bs4 import BeautifulSoup
from tqdm import tqdm

# ========================= CONFIG =========================
DATA_DIR = Path(r"D:\pfe2026\data\DC\data_clean\pages")
OUTPUT_DIR = Path(r"D:\pfe2026\data_images")
METADATA_PATH = OUTPUT_DIR / "metadata_images.json"
LOG_FILE = OUTPUT_DIR / "extraction.log"

# ========================= LOGGING =========================
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ========================= IMAGE DETECTION =========================
IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': ('png', 'image/png'),
    b'\xFF\xD8\xFF': ('jpg', 'image/jpeg'),
    b'GIF87a': ('gif', 'image/gif'),
    b'GIF89a': ('gif', 'image/gif'),
    b'BM': ('bmp', 'image/bmp'),
    b'RIFF': ('webp', 'image/webp'),  # Needs further check
    b'<svg': ('svg', 'image/svg+xml'),
    b'<?xml': ('svg', 'image/svg+xml'),
}

def detect_image_type(data: bytes) -> tuple:
    """
    Détecte le type d'image à partir des magic bytes.
    Retourne (extension, mime_type) ou (None, None)
    """
    if not data or len(data) < 8:
        return None, None
    
    # PNG
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'image/png'
    
    # JPEG
    if data.startswith(b'\xFF\xD8\xFF'):
        return 'jpg', 'image/jpeg'
    
    # GIF
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'gif', 'image/gif'
    
    # BMP
    if data.startswith(b'BM'):
        return 'bmp', 'image/bmp'
    
    # WebP
    if data.startswith(b'RIFF') and b'WEBP' in data[:12]:
        return 'webp', 'image/webp'
    
    # SVG
    if data.startswith(b'<svg') or (data.startswith(b'<?xml') and b'<svg' in data[:200]):
        return 'svg', 'image/svg+xml'
    
    return None, None

def is_likely_image(data: bytes) -> bool:
    """Vérifie si les données ressemblent à une image."""
    ext, mime = detect_image_type(data)
    return ext is not None

# ========================= EXTRACTION MHTML PARTS =========================
def extract_images_from_mhtml_parts(msg, doc_path: Path, relative_doc_path: Path):
    """
    Extrait images depuis MIME parts.
    Traite aussi les application/octet-stream qui sont en fait des images.
    """
    images_meta = []
    image_counter = 0
    
    image_base_dir = OUTPUT_DIR / relative_doc_path.parent / doc_path.stem
    image_base_dir.mkdir(parents=True, exist_ok=True)
    
    for part in msg.walk():
        content_type = part.get_content_type()
        
        # Cas 1: Content-type image explicite
        is_image_mime = content_type.startswith("image/")
        
        # Cas 2: application/octet-stream qui pourrait être une image
        is_octet_stream = content_type == "application/octet-stream"
        
        if is_image_mime or is_octet_stream:
            try:
                payload = part.get_payload(decode=True)
                
                if not payload or len(payload) < 100:
                    continue
                
                # Pour octet-stream, vérifier que c'est vraiment une image
                if is_octet_stream:
                    detected_ext, detected_mime = detect_image_type(payload)
                    if detected_ext is None:
                        # Pas une image, on ignore
                        continue
                    ext = detected_ext
                    actual_mime = detected_mime
                else:
                    # Content-type image explicite
                    ext_map = {
                        'image/png': 'png',
                        'image/jpeg': 'jpg',
                        'image/jpg': 'jpg',
                        'image/gif': 'gif',
                        'image/bmp': 'bmp',
                        'image/webp': 'webp',
                        'image/svg+xml': 'svg'
                    }
                    ext = ext_map.get(content_type, None)
                    if ext is None:
                        # Fallback sur détection magic bytes
                        ext, actual_mime = detect_image_type(payload)
                        if ext is None:
                            continue
                    else:
                        actual_mime = content_type
                
                image_counter += 1
                image_id = f"img_{image_counter:03d}"
                image_filename = f"{image_id}.{ext}"
                image_path = image_base_dir / image_filename
                
                with open(image_path, "wb") as img_file:
                    img_file.write(payload)
                
                images_meta.append({
                    "doc_id": doc_path.name,
                    "relative_doc_path": str(relative_doc_path),
                    "space": relative_doc_path.parts[0] if len(relative_doc_path.parts) > 0 else "root",
                    "image_id": image_id,
                    "order_in_doc": image_counter,
                    "content_type": actual_mime,
                    "original_content_type": content_type,
                    "extension": ext,
                    "size_bytes": len(payload),
                    "source": "octet_stream" if is_octet_stream else "mhtml_part",
                    "image_path": str(image_path.relative_to(OUTPUT_DIR))
                })
                
                logger.debug(f"  🖼 {image_filename} ({len(payload)} bytes) [{content_type} → {actual_mime}]")
                
            except Exception as e:
                logger.warning(f"  ⚠️ Erreur extraction part: {e}")
    
    return images_meta, image_counter

# ========================= EXTRACTION HTML BASE64 =========================
def extract_images_from_html(html_content: str, doc_path: Path, relative_doc_path: Path, start_counter: int):
    """Extrait images base64 depuis HTML."""
    images_meta = []
    image_counter = start_counter
    
    image_base_dir = OUTPUT_DIR / relative_doc_path.parent / doc_path.stem
    image_base_dir.mkdir(parents=True, exist_ok=True)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Images dans <img src="data:image/...">
    img_tags = soup.find_all('img')
    for img in img_tags:
        src = img.get('src', '')
        
        if 'data:image' in src:
            try:
                match = re.search(r'data:image/([^;,]+)(?:;base64)?,([A-Za-z0-9+/=\s]+)', src, re.DOTALL)
                if not match:
                    continue
                
                img_format = match.group(1).lower()
                img_data = match.group(2).replace(' ', '').replace('\n', '').replace('\r', '')
                
                payload = base64.b64decode(img_data)
                
                if len(payload) < 100:
                    continue
                
                # Vérifier le type réel
                detected_ext, detected_mime = detect_image_type(payload)
                if detected_ext:
                    ext = detected_ext
                    actual_mime = detected_mime
                else:
                    ext = img_format
                    actual_mime = f"image/{img_format}"
                
                image_counter += 1
                image_id = f"img_{image_counter:03d}"
                image_filename = f"{image_id}.{ext}"
                image_path = image_base_dir / image_filename
                
                with open(image_path, "wb") as img_file:
                    img_file.write(payload)
                
                images_meta.append({
                    "doc_id": doc_path.name,
                    "relative_doc_path": str(relative_doc_path),
                    "space": relative_doc_path.parts[0] if len(relative_doc_path.parts) > 0 else "root",
                    "image_id": image_id,
                    "order_in_doc": image_counter,
                    "content_type": actual_mime,
                    "extension": ext,
                    "size_bytes": len(payload),
                    "source": "base64_html",
                    "image_path": str(image_path.relative_to(OUTPUT_DIR))
                })
                
                logger.debug(f"  🖼 HTML: {image_filename} ({len(payload)} bytes)")
                
            except Exception as e:
                logger.warning(f"  ⚠️ Erreur base64: {e}")
    
    return images_meta, image_counter

# ========================= EXTRACTION PRINCIPALE =========================
def extract_images_from_doc(doc_path: Path):
    """Extrait toutes les images d'un fichier .doc MHTML."""
    all_images_meta = []
    
    try:
        with open(doc_path, "rb") as f:
            raw_content = f.read()
        
        relative_doc_path = doc_path.relative_to(DATA_DIR)
        
        # Parser MHTML
        msg = email.message_from_bytes(raw_content, policy=policy.default)
        
        # Méthode 1: Extraire depuis MIME parts (y compris octet-stream)
        images_from_mime, counter = extract_images_from_mhtml_parts(msg, doc_path, relative_doc_path)
        all_images_meta.extend(images_from_mime)
        
        # Méthode 2: Extraire depuis HTML base64
        html_content = None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ['text/html', 'text/x-html']:
                    try:
                        html_content = part.get_content()
                        break
                    except:
                        try:
                            html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                        except:
                            pass
        else:
            if msg.get_content_type() in ['text/html', 'text/x-html']:
                try:
                    html_content = msg.get_content()
                except:
                    html_content = raw_content.decode('utf-8', errors='ignore')
        
        if html_content and '<img' in html_content:
            images_from_html, final_counter = extract_images_from_html(
                html_content, doc_path, relative_doc_path, counter
            )
            all_images_meta.extend(images_from_html)
        
        if all_images_meta:
            logger.info(f"✅ {relative_doc_path}: {len(all_images_meta)} images")
        
        return all_images_meta
    
    except Exception as e:
        logger.error(f"❌ {doc_path.name}: {e}")
        return []

# ========================= MAIN =========================
def main():
    logger.info("="*70)
    logger.info("🚀 EXTRACTION IMAGES - SUPPORT OCTET-STREAM")
    logger.info("="*70)
    logger.info(f"Source: {DATA_DIR}")
    logger.info(f"Destination: {OUTPUT_DIR}")
    logger.info("="*70)
    
    doc_files = list(DATA_DIR.rglob("*.doc"))
    logger.info(f"\n📂 {len(doc_files)} fichiers .doc trouvés")
    logger.info("\n🔄 Début extraction...\n")
    
    # Extraction
    all_metadata = []
    stats = {
        "total_docs": len(doc_files),
        "docs_with_images": 0,
        "total_images": 0,
        "images_by_format": {},
        "images_by_source": {},
        "total_size_mb": 0,
        "errors": 0
    }
    
    for doc_file in tqdm(doc_files, desc="Extraction"):
        try:
            images_meta = extract_images_from_doc(doc_file)
            if images_meta:
                stats["docs_with_images"] += 1
                stats["total_images"] += len(images_meta)
                
                for img in images_meta:
                    ext = img["extension"]
                    src = img.get("source", "unknown")
                    size_mb = img["size_bytes"] / (1024 * 1024)
                    
                    stats["images_by_format"][ext] = stats["images_by_format"].get(ext, 0) + 1
                    stats["images_by_source"][src] = stats["images_by_source"].get(src, 0) + 1
                    stats["total_size_mb"] += size_mb
                
                all_metadata.extend(images_meta)
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"❌ {doc_file.name}: {e}")
    
    # Sauvegarder résultats
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, indent=2, ensure_ascii=False)
    
    stats_file = OUTPUT_DIR / "extraction_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    # Résumé
    logger.info("\n" + "="*70)
    logger.info("✅ EXTRACTION TERMINÉE")
    logger.info("="*70)
    logger.info(f"📄 Documents traités: {stats['total_docs']}")
    logger.info(f"📄 Documents avec images: {stats['docs_with_images']}")
    logger.info(f"🖼️ Images extraites: {stats['total_images']}")
    logger.info(f"💾 Taille totale: {stats['total_size_mb']:.2f} MB")
    
    if stats['images_by_format']:
        logger.info(f"\n📊 Images par format:")
        for fmt, count in sorted(stats['images_by_format'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"   {fmt.upper()}: {count}")
    
    if stats['images_by_source']:
        logger.info(f"\n📊 Images par source:")
        for src, count in sorted(stats['images_by_source'].items(), key=lambda x: x[1], reverse=True):
            logger.info(f"   {src}: {count}")
    
    logger.info(f"\n❌ Erreurs: {stats['errors']}")
    logger.info(f"\n📁 Dossier images: {OUTPUT_DIR}")
    logger.info(f"📝 Metadata: {METADATA_PATH}")
    logger.info("="*70)

if __name__ == "__main__":
    main()