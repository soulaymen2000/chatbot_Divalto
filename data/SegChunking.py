#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chunker SÉMANTIQUE Intelligent avec BGE-M3 - VERSION ULTRA-RAPIDE + TRACKING MÉDIAS
✔ SEMANTIC CHUNKING: découpe intelligente par sections, paragraphes, contexte
✔ Multiprocessing pour exploiter tous les cœurs
✔ SÉPARATION des sources: chaque input_dir → son propre dossier de sortie
✔ Détection précise des positions images/tables avec contexte
✔ Préserve les structures: listes, tables, code blocks
✔ Overlap géré sémantiquement (contexte partagé)
"""
import os
import sys
import json
import logging
import re
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

import torch
from transformers import AutoTokenizer
from tqdm import tqdm
import email
from email import policy
from bs4 import BeautifulSoup

# =========================
# CONFIG
# =========================
CHUNK_SIZE = 600
OVERLAP = 80
MAX_CHUNK_SIZE = 800  # Taille max pour chunks sémantiques

# Configuration avec noms explicites pour la séparation
INPUT_CONFIGS = [
    {
        "name": "donneFonctionnel",
        "input_dir": Path(r"D:\pfe2026\data\DC\donneFonctionnel\data_clean"),
        "output_dir": Path(r"D:\pfe2026\data\DC\data_semanticchunked\donneFonctionnel")
    },
    {
        "name": "donnerCodage",
        "input_dir": Path(r"D:\pfe2026\data\DC\donnerCodage\CHM_EXTRACTED\text"),
        "output_dir": Path(r"D:\pfe2026\data\DC\data_semanticchunked\donnerCodage")
    }
]

LOG_DIR = Path(r"D:\pfe2026\data\DC\data_semanticchunked\logs\chunking")

TOKENIZER_NAME = "BAAI/bge-m3"

# Markers pour contenu spécial
MARKERS = ("[IMAGE", "[TABLE", "[CODE", "[DIAGRAM")

# Nombre de workers
MAX_WORKERS = min(os.cpu_count() or 4, 8)

SUPPORTED_EXTENSIONS = {".txt", ".doc"}

# =========================
# LOGGING SETUP
# =========================
LOG_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"semantic_chunking_{TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger("SemanticChunker")

# Regex pour nettoyer le MHTML avant BeautifulSoup
RE_BASE64_IMAGE = re.compile(r'src="data:image/[^"]+"', re.IGNORECASE)
RE_BASE64_MIME = re.compile(r'Content-Transfer-Encoding: base64[\s\n]+[A-Za-z0-9+/=\s]{500,}', re.MULTILINE)

# =========================
# GPU CHECK
# =========================
def check_gpu() -> torch.device:
    """
    Détecte le device disponible (GPU/CPU)
    Centralisé pour usage futur (embeddings, FAISS GPU, etc.)
    """
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"🔥 GPU détecté: {torch.cuda.get_device_name(0)}")
    else:
        device = torch.device("cpu")
        logger.info("💻 GPU non disponible → CPU")
    return device

# =========================
# TEXT EXTRACTION (avec insertion de markers)
# =========================
def extract_text_from_doc(path: Path) -> str:
    """
    Extrait le texte d'un fichier .doc (MHTML) avec pré-nettoyage
    ✅ INSÈRE DES MARKERS [IMAGE] et [TABLE] avant extraction pour tracking
    """
    try:
        with open(path, 'rb') as f:
            content_bytes = f.read()

        try:
            content_str = content_bytes.decode('utf-8', errors='ignore')
            content_str = RE_BASE64_IMAGE.sub('src="[BASE64_REMOVED]"', content_str)
            content_str = RE_BASE64_MIME.sub('Content-Transfer-Encoding: [REMOVED]', content_str)
            cleaned_bytes = content_str.encode('utf-8', errors='ignore')
        except:
            cleaned_bytes = content_bytes

        msg = email.message_from_bytes(cleaned_bytes, policy=policy.default)
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
            html_content = cleaned_bytes.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Supprimer les éléments non-texte
        for element in soup(['script', 'style', 'meta', 'link', 'noscript']):
            element.decompose()
        
        # ✅ INSÉRER DES MARKERS POUR LES IMAGES
        img_counter = 0
        for img in soup.find_all('img'):
            img_counter += 1
            # Extraire le nom de fichier si disponible
            src = img.get('src', '')
            alt = img.get('alt', '')
            if alt:
                marker_name = alt[:50]
            elif src and not src.startswith('data:'):
                marker_name = src.split('/')[-1].split('?')[0][:50]
            else:
                marker_name = f"img_{img_counter}"
            # Remplacer l'image par un marker
            img.replace_with(f" [IMAGE: {marker_name}] ")
        
        # ✅ INSÉRER DES MARKERS POUR LES TABLES
        table_counter = 0
        for table in soup.find_all('table'):
            table_counter += 1
            # Extraire un aperçu des headers si disponibles
            headers = []
            for th in table.find_all('th')[:3]:
                header_text = th.get_text(strip=True)[:20]
                if header_text:
                    headers.append(header_text)
            
            if headers:
                table_marker = f" [TABLE: {', '.join(headers)}] "
            else:
                # Prendre les premiers TD comme aperçu
                first_row = table.find('tr')
                if first_row:
                    cells = [td.get_text(strip=True)[:15] for td in first_row.find_all('td')[:3]]
                    if cells:
                        table_marker = f" [TABLE: {', '.join(cells)}] "
                    else:
                        table_marker = f" [TABLE: table_{table_counter}] "
                else:
                    table_marker = f" [TABLE: table_{table_counter}] "
            
            # Extraire le contenu de la table puis ajouter le marker
            table_text = table.get_text(separator=' ', strip=True)
            table.replace_with(f"{table_marker} {table_text} ")

        text = soup.get_text(separator=' ', strip=True)
        return ' '.join(text.split())

    except Exception as e:
        return ""

def extract_text(path: Path) -> str:
    """Route vers la bonne fonction d'extraction"""
    ext = path.suffix.lower()
    if ext == '.txt':
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except:
            return ""
    elif ext == '.doc':
        return extract_text_from_doc(path)
    return ""

# =========================
# MEDIA DETECTION - DÉTECTION PRÉCISE DES POSITIONS
# =========================
def find_media_positions(chunk: str, chunk_start_pos: int) -> Dict:
    """
    ✅ Détection précise des positions images/tables avec contexte complet
    
    Pour chaque image et table, capture:
    - Position en caractères (relative au chunk)
    - Position absolue dans le document original
    - Numéro de ligne
    - Contexte avant (50 caractères)
    - Contexte après (50 caractères)
    - ID/nom si disponible dans le marker
    """
    images = []
    tables = []
    
    # ========== DÉTECTION DES IMAGES ==========
    for match in re.finditer(r'\[IMAGE[^\]]*\]', chunk):
        image_text = match.group(0)
        start_pos = match.start()
        end_pos = match.end()
        lines_before = chunk[:start_pos].count('\n')
        
        # Extraction du contexte avant/après
        context_start = max(0, start_pos - 50)
        context_end = min(len(chunk), end_pos + 50)
        context_before = chunk[context_start:start_pos].strip()
        context_after = chunk[end_pos:context_end].strip()
        
        # Extraction de l'ID de l'image depuis le marker
        image_id = None
        id_match = re.search(r'\[IMAGE[:\s]+([^\]]+)\]', image_text)
        if id_match:
            image_id = id_match.group(1).strip()
        else:
            image_id = f"image_{len(images) + 1}"
        
        image_info = {
            'marker': image_text,
            'image_id': image_id,
            'char_position': start_pos,
            'absolute_char_position': chunk_start_pos + start_pos,
            'line_number': lines_before + 1,
            'context_before': context_before,
            'context_after': context_after,
            'marker_length': len(image_text)
        }
        
        images.append(image_info)
    
    # ========== DÉTECTION DES TABLES MARQUÉES ==========
    for match in re.finditer(r'\[TABLE[^\]]*\]', chunk):
        table_text = match.group(0)
        start_pos = match.start()
        end_pos = match.end()
        lines_before = chunk[:start_pos].count('\n')
        
        # Extraction du contexte
        context_start = max(0, start_pos - 50)
        context_end = min(len(chunk), end_pos + 50)
        context_before = chunk[context_start:start_pos].strip()
        context_after = chunk[end_pos:context_end].strip()
        
        # Extraction de l'ID de la table
        table_id = None
        id_match = re.search(r'\[TABLE[:\s]+([^\]]+)\]', table_text)
        if id_match:
            table_id = id_match.group(1).strip()
        else:
            table_id = f"table_{len(tables) + 1}"
        
        table_info = {
            'marker': table_text,
            'table_id': table_id,
            'char_position': start_pos,
            'absolute_char_position': chunk_start_pos + start_pos,
            'line_number': lines_before + 1,
            'context_before': context_before,
            'context_after': context_after,
            'marker_length': len(table_text)
        }
        
        tables.append(table_info)
    
    # ========== DÉTECTION DES TABLES MARKDOWN/ASCII ==========
    markdown_tables = []
    lines = chunk.split('\n')
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        # Détection de lignes contenant des pipes (tables markdown)
        if '|' in line_stripped and line_stripped.count('|') >= 2:
            # Calculer la position en caractères
            char_pos = sum(len(lines[j]) + 1 for j in range(i))
            
            markdown_tables.append({
                'type': 'markdown_table',
                'line_number': i + 1,
                'char_position': char_pos,
                'absolute_char_position': chunk_start_pos + char_pos,
                'content_preview': line_stripped[:100] + ('...' if len(line_stripped) > 100 else ''),
                'pipe_count': line_stripped.count('|')
            })
    
    # ========== DÉTECTION DES CODE BLOCKS ==========
    code_blocks = []
    for match in re.finditer(r'\[CODE[^\]]*\]', chunk):
        code_text = match.group(0)
        start_pos = match.start()
        end_pos = match.end()
        lines_before = chunk[:start_pos].count('\n')
        
        context_before = chunk[max(0, start_pos - 50):start_pos].strip()
        context_after = chunk[end_pos:min(len(chunk), end_pos + 50)].strip()
        
        code_id = None
        id_match = re.search(r'\[CODE[:\s]+([^\]]+)\]', code_text)
        if id_match:
            code_id = id_match.group(1).strip()
        else:
            code_id = f"code_{len(code_blocks) + 1}"
        
        code_blocks.append({
            'marker': code_text,
            'code_id': code_id,
            'char_position': start_pos,
            'absolute_char_position': chunk_start_pos + start_pos,
            'line_number': lines_before + 1,
            'context_before': context_before,
            'context_after': context_after
        })
    
    return {
        'images': images,
        'tables': tables,
        'markdown_tables': markdown_tables,
        'code_blocks': code_blocks,
        'total_images': len(images),
        'total_tables': len(tables) + len(markdown_tables),
        'total_code_blocks': len(code_blocks),
        'has_media': len(images) > 0 or len(tables) > 0 or len(markdown_tables) > 0
    }

# =========================
# SEMANTIC SECTION DETECTION
# =========================
class SemanticChunker:
    """Chunker sémantique intelligent"""
    
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
    
    def detect_sections(self, text: str) -> List[Dict]:
        """
        Détecte les sections sémantiques dans le texte
        Retourne: [{'title': str, 'content': str, 'start_pos': int, 'type': str}]
        """
        sections = []
        
        # Patterns pour détecter les titres/sections
        title_patterns = [
            (r'^#{1,6}\s+(.+)$', 'markdown_header'),           # # Titre
            (r'^([A-Z][A-Z\s]{3,})$', 'uppercase_title'),      # TITRE MAJUSCULES
            (r'^(\d+\.?\s+[A-Z].+)$', 'numbered_section'),     # 1. Section
            (r'^([IVX]+\.\s+[A-Z].+)$', 'roman_section'),      # I. Section
            (r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*):$', 'colon_title'),  # Titre:
        ]
        
        lines = text.split('\n')
        current_section = {'start_pos': 0, 'title': '', 'content': [], 'type': 'prose'}
        char_position = 0
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Vérifier si c'est un titre
            is_title = False
            section_type = 'prose'
            
            for pattern, ptype in title_patterns:
                if re.match(pattern, line_stripped, re.MULTILINE):
                    is_title = True
                    section_type = ptype
                    break
            
            if is_title and current_section['content']:
                # Sauvegarder la section précédente
                sections.append({
                    'title': current_section['title'],
                    'content': '\n'.join(current_section['content']),
                    'start_pos': current_section['start_pos'],
                    'type': current_section['type']
                })
                # Nouvelle section
                current_section = {
                    'start_pos': char_position,
                    'title': line_stripped,
                    'content': [],
                    'type': section_type
                }
            else:
                current_section['content'].append(line)
            
            char_position += len(line) + 1  # +1 pour \n
        
        # Dernière section
        if current_section['content']:
            sections.append({
                'title': current_section['title'],
                'content': '\n'.join(current_section['content']),
                'start_pos': current_section['start_pos'],
                'type': current_section['type']
            })
        
        return sections if sections else [{'title': '', 'content': text, 'start_pos': 0, 'type': 'prose'}]
    
    def detect_content_type(self, text: str) -> str:
        """Détecte le type de contenu d'un segment"""
        if '[CODE' in text or '```' in text or re.search(r'^\s{4,}', text, re.MULTILINE):
            return 'code'
        elif '[TABLE' in text or ('|' in text and text.count('|') >= 4):
            return 'table'
        elif re.search(r'^\s*[-*•]\s', text, re.MULTILINE):
            return 'bullet_list'
        elif re.search(r'^\s*\d+[.)]\s', text, re.MULTILINE):
            return 'numbered_list'
        elif '[IMAGE' in text:
            return 'image_section'
        else:
            return 'prose'
    
    def extract_semantic_units(self, text: str) -> List[Dict]:
        """
        Extrait les unités sémantiques (paragraphes, listes, tables, code)
        """
        units = []
        current_pos = 0
        
        # Séparer par double saut de ligne (paragraphes)
        segments = re.split(r'\n\n+', text)
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            content_type = self.detect_content_type(segment)
            
            units.append({
                'content': segment,
                'type': content_type,
                'start_pos': current_pos,
                'tokens': len(self.tokenizer.encode(segment, add_special_tokens=False))
            })
            
            current_pos += len(segment) + 2  # +2 pour \n\n
        
        return units
    
    def chunk_semantic(self, text: str) -> List[Dict]:
        """
        Découpage sémantique principal
        Retourne: [{'text': str, 'start_pos': int, 'section_title': str, 'content_type': str}]
        """
        if not text or len(text.strip()) < 20:
            return []
        
        # 1. Détecter les sections
        sections = self.detect_sections(text)
        
        chunks = []
        
        # 2. Pour chaque section, créer des chunks sémantiques
        for section in sections:
            section_text = section['content']
            section_title = section['title']
            section_start = section['start_pos']
            
            # Tokeniser la section
            section_tokens = self.tokenizer.encode(section_text, add_special_tokens=False)
            
            if len(section_tokens) <= CHUNK_SIZE:
                # Section assez petite
                chunks.append({
                    'text': section_text,
                    'start_pos': section_start,
                    'section_title': section_title,
                    'content_type': self.detect_content_type(section_text)
                })
            else:
                # Section trop grande → découper sémantiquement
                semantic_units = self.extract_semantic_units(section_text)
                
                current_chunk = []
                current_tokens = 0
                current_chunk_start = section_start
                
                for unit in semantic_units:
                    unit_tokens = unit['tokens']
                    
                    # Si ajouter cette unité dépasse la limite
                    if current_tokens + unit_tokens > CHUNK_SIZE and current_chunk:
                        # Sauvegarder le chunk actuel
                        chunk_text = '\n\n'.join([u['content'] for u in current_chunk])
                        chunks.append({
                            'text': chunk_text,
                            'start_pos': current_chunk_start,
                            'section_title': section_title,
                            'content_type': current_chunk[0]['type']
                        })
                        
                        # Nouveau chunk avec overlap (garder dernière unité pour contexte)
                        if OVERLAP > 0 and current_chunk:
                            current_chunk = [current_chunk[-1], unit]
                            current_tokens = current_chunk[-2]['tokens'] + unit_tokens
                            current_chunk_start = current_chunk[-2]['start_pos']
                        else:
                            current_chunk = [unit]
                            current_tokens = unit_tokens
                            current_chunk_start = unit['start_pos']
                    
                    # Si l'unité seule dépasse MAX_CHUNK_SIZE, la découper aux phrases
                    elif unit_tokens > MAX_CHUNK_SIZE:
                        # Sauvegarder le chunk actuel si non vide
                        if current_chunk:
                            chunk_text = '\n\n'.join([u['content'] for u in current_chunk])
                            chunks.append({
                                'text': chunk_text,
                                'start_pos': current_chunk_start,
                                'section_title': section_title,
                                'content_type': current_chunk[0]['type']
                            })
                            current_chunk = []
                            current_tokens = 0
                        
                        # Découper l'unité aux phrases
                        sentences = [s.strip() + '.' for s in unit['content'].split('.') if s.strip()]
                        sent_chunk = []
                        sent_tokens = 0
                        
                        for sent in sentences:
                            sent_tok = len(self.tokenizer.encode(sent, add_special_tokens=False))
                            if sent_tokens + sent_tok <= CHUNK_SIZE:
                                sent_chunk.append(sent)
                                sent_tokens += sent_tok
                            else:
                                if sent_chunk:
                                    chunks.append({
                                        'text': ' '.join(sent_chunk),
                                        'start_pos': unit['start_pos'],
                                        'section_title': section_title,
                                        'content_type': unit['type']
                                    })
                                sent_chunk = [sent]
                                sent_tokens = sent_tok
                        
                        if sent_chunk:
                            chunks.append({
                                'text': ' '.join(sent_chunk),
                                'start_pos': unit['start_pos'],
                                'section_title': section_title,
                                'content_type': unit['type']
                            })
                        
                        current_chunk_start = unit['start_pos'] + len(unit['content'])
                    else:
                        # Ajouter l'unité au chunk actuel
                        current_chunk.append(unit)
                        current_tokens += unit_tokens
                
                # Sauvegarder le dernier chunk
                if current_chunk:
                    chunk_text = '\n\n'.join([u['content'] for u in current_chunk])
                    chunks.append({
                        'text': chunk_text,
                        'start_pos': current_chunk_start,
                        'section_title': section_title,
                        'content_type': current_chunk[0]['type']
                    })
        
        return chunks

# =========================
# WORKER FUNCTION
# =========================
_tokenizer = None
_semantic_chunker = None

def get_chunker():
    """Lazy loading du chunker (une fois par processus)"""
    global _tokenizer, _semantic_chunker
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME, trust_remote_code=True)
        _semantic_chunker = SemanticChunker(_tokenizer)
    return _tokenizer, _semantic_chunker

def process_file_worker(file_info: Tuple[Path, Path, Path, torch.device]) -> Dict:
    """
    Fonction exécutée par les processus fils
    """
    file_path, input_root, output_root, device = file_info
    
    try:
        tokenizer, semantic_chunker = get_chunker()
        text = extract_text(file_path)
        
        if not text or len(text.strip()) < 20:
            return {'status': 'skipped', 'file': str(file_path)}
        
        # SEMANTIC CHUNKING
        chunks_with_meta = semantic_chunker.chunk_semantic(text)
        
        if not chunks_with_meta:
            return {'status': 'skipped', 'file': str(file_path)}

        # Calculer le chemin de sortie EN PRÉSERVANT la hiérarchie
        relative_path = file_path.relative_to(input_root)
        output_dir = output_root / relative_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        base_name = file_path.stem
        total_tokens = 0
        total_images = 0
        total_tables = 0
        total_code_blocks = 0
        
        for idx, chunk_data in enumerate(chunks_with_meta, start=1):
            chunk_text = chunk_data['text']
            chunk_start_pos = chunk_data['start_pos']
            chunk_name = f"{base_name}_chunk_{idx:03d}"
            
            # Sauvegarder le chunk
            (output_dir / f"{chunk_name}.txt").write_text(chunk_text, encoding='utf-8')
            
            # ✅ DÉTECTION PRÉCISE DES POSITIONS DES MÉDIAS
            media_positions = find_media_positions(chunk_text, chunk_start_pos)
            
            # Métadonnées enrichies
            token_count = len(tokenizer.encode(chunk_text, add_special_tokens=False))
            total_tokens += token_count
            total_images += media_positions['total_images']
            total_tables += media_positions['total_tables']
            total_code_blocks += media_positions['total_code_blocks']
            
            # ✅ Résumés compacts pour affichage rapide
            image_summary = [
                {
                    "image_id": img['image_id'],
                    "line": img['line_number'],
                    "position": img['char_position'],
                    "abs_position": img['absolute_char_position']
                }
                for img in media_positions['images']
            ]
            
            table_summary = [
                {
                    "table_id": tbl['table_id'],
                    "line": tbl['line_number'],
                    "position": tbl['char_position'],
                    "abs_position": tbl['absolute_char_position']
                }
                for tbl in media_positions['tables']
            ]
            
            # ✅ MÉTADONNÉES COMPLÈTES AVEC POSITIONS PRÉCISES
            metadata = {
                # Informations de base
                "source_file": file_path.name,
                "chunk_id": idx,
                "total_chunks": len(chunks_with_meta),
                "original_path": str(relative_path),
                
                # Statistiques
                "token_count": token_count,
                "char_count": len(chunk_text),
                "chunk_start_position": chunk_start_pos,
                
                # Métadonnées sémantiques
                "section_title": chunk_data.get('section_title', ''),
                "content_type": chunk_data.get('content_type', 'prose'),
                "chunking_method": "semantic",
                
                # ✅ COMPTEURS DE MÉDIAS
                "total_images": media_positions['total_images'],
                "total_tables": media_positions['total_tables'],
                "total_code_blocks": media_positions['total_code_blocks'],
                "has_media": media_positions['has_media'],
                
                # ✅ RÉSUMÉS COMPACTS (pour affichage rapide)
                "image_summary": image_summary,
                "table_summary": table_summary,
                
                # ✅ POSITIONS DÉTAILLÉES DES IMAGES (avec contexte complet)
                "images_detailed": [
                    {
                        "image_id": img['image_id'],
                        "marker": img['marker'],
                        "position": {
                            "char_in_chunk": img['char_position'],
                            "char_absolute": img['absolute_char_position'],
                            "line_number": img['line_number']
                        },
                        "context": {
                            "before": img['context_before'],
                            "after": img['context_after']
                        },
                        "marker_length": img['marker_length']
                    }
                    for img in media_positions['images']
                ],
                
                # ✅ POSITIONS DÉTAILLÉES DES TABLES (avec contexte complet)
                "tables_detailed": [
                    {
                        "table_id": tbl['table_id'],
                        "marker": tbl['marker'],
                        "position": {
                            "char_in_chunk": tbl['char_position'],
                            "char_absolute": tbl['absolute_char_position'],
                            "line_number": tbl['line_number']
                        },
                        "context": {
                            "before": tbl['context_before'],
                            "after": tbl['context_after']
                        },
                        "marker_length": tbl['marker_length']
                    }
                    for tbl in media_positions['tables']
                ],
                
                # ✅ TABLES MARKDOWN DÉTECTÉES
                "markdown_tables": [
                    {
                        "type": mt['type'],
                        "line_number": mt['line_number'],
                        "char_position": mt['char_position'],
                        "absolute_position": mt['absolute_char_position'],
                        "preview": mt['content_preview'],
                        "pipe_count": mt['pipe_count']
                    }
                    for mt in media_positions['markdown_tables']
                ],
                
                # ✅ CODE BLOCKS DÉTECTÉS
                "code_blocks": [
                    {
                        "code_id": cb['code_id'],
                        "marker": cb['marker'],
                        "position": {
                            "char_in_chunk": cb['char_position'],
                            "char_absolute": cb['absolute_char_position'],
                            "line_number": cb['line_number']
                        },
                        "context": {
                            "before": cb['context_before'],
                            "after": cb['context_after']
                        }
                    }
                    for cb in media_positions['code_blocks']
                ],
                
                "chunked_at": datetime.now().isoformat()
            }
            
            # Sauvegarder les métadonnées
            (output_dir / f"{chunk_name}.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

        return {
            'status': 'success',
            'file': str(file_path),
            'chunks': len(chunks_with_meta),
            'tokens': total_tokens,
            'images': total_images,
            'tables': total_tables,
            'code_blocks': total_code_blocks
        }
        
    except Exception as e:
        logger.error(f"Erreur sur {file_path}: {e}")
        return {
            'status': 'error',
            'file': str(file_path),
            'error': str(e)
        }

# =========================
# PROCESS DIRECTORY
# =========================
def process_directory(config: Dict, device: torch.device) -> Dict:
    """Traite un dossier d'entrée"""
    name = config['name']
    input_dir = config['input_dir']
    output_dir = config['output_dir']
    
    logger.info("=" * 80)
    logger.info(f"📂 SOURCE: {name}")
    logger.info(f"   Input:  {input_dir}")
    logger.info(f"   Output: {output_dir}")
    logger.info("=" * 80)
    
    if not input_dir.exists():
        logger.error(f"❌ Dossier introuvable: {input_dir}")
        return {'name': name, 'error': 'input_not_found'}
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    files = [
        (f, input_dir, output_dir, device)
        for f in input_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    
    if not files:
        logger.warning(f"⚠️ Aucun fichier trouvé dans {input_dir}")
        return {'name': name, 'total': 0, 'success': 0}
    
    logger.info(f"📄 {len(files)} fichiers trouvés")
    
    stats = {
        'name': name,
        'total': len(files),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'total_chunks': 0,
        'total_tokens': 0,
        'total_images': 0,
        'total_tables': 0,
        'total_code_blocks': 0
    }
    
    start_time = time.time()
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file_worker, f_info): f_info for f_info in files}
        
        with tqdm(total=len(files), desc=f"Semantic Chunking {name}", unit="files") as pbar:
            for future in as_completed(futures):
                result = future.result()
                
                if result['status'] == 'success':
                    stats['success'] += 1
                    stats['total_chunks'] += result['chunks']
                    stats['total_tokens'] += result['tokens']
                    stats['total_images'] += result.get('images', 0)
                    stats['total_tables'] += result.get('tables', 0)
                    stats['total_code_blocks'] += result.get('code_blocks', 0)
                elif result['status'] == 'skipped':
                    stats['skipped'] += 1
                elif result['status'] == 'error':
                    stats['failed'] += 1
                
                pbar.update(1)
    
    duration = time.time() - start_time
    
    logger.info(f"\n✅ Traitement terminé en {duration:.1f}s")
    logger.info(f"   Fichiers traités: {stats['success']}/{stats['total']}")
    logger.info(f"   Chunks créés: {stats['total_chunks']:,}")
    logger.info(f"   Tokens totaux: {stats['total_tokens']:,}")
    logger.info(f"   Images détectées: {stats['total_images']:,} (avec positions)")
    logger.info(f"   Tables détectées: {stats['total_tables']:,} (avec positions)")
    logger.info(f"   Code blocks: {stats['total_code_blocks']:,}")
    logger.info(f"   Vitesse: {stats['success']/duration:.2f} fichiers/s")
    
    if stats['skipped'] > 0:
        logger.info(f"   ⚠️ Fichiers ignorés: {stats['skipped']}")
    if stats['failed'] > 0:
        logger.info(f"   ❌ Erreurs: {stats['failed']}")
    
    return stats

# =========================
# MAIN
# =========================
def main():
    """Point d'entrée principal"""
    logger.info("=" * 80)
    logger.info("CHUNKER SÉMANTIQUE - DÉCOUPAGE INTELLIGENT")
    logger.info("✅ DÉTECTION PRÉCISE DES POSITIONS IMAGES/TABLES/CODE")
    logger.info("=" * 80)
    logger.info(f"📝 Configuration:")
    logger.info(f"   Chunk size: {CHUNK_SIZE} tokens")
    logger.info(f"   Max chunk size: {MAX_CHUNK_SIZE} tokens")
    logger.info(f"   Overlap: {OVERLAP} tokens (sémantique)")
    logger.info(f"   Workers: {MAX_WORKERS}")
    logger.info(f"   Tokenizer: {TOKENIZER_NAME}")
    logger.info(f"   Méthode: SEMANTIC CHUNKING")
    logger.info("=" * 80)
    logger.info("🎯 Détection des médias:")
    logger.info("   ✅ Position en caractères (relative au chunk)")
    logger.info("   ✅ Position absolue dans le document original")
    logger.info("   ✅ Numéro de ligne")
    logger.info("   ✅ Contexte avant (50 caractères)")
    logger.info("   ✅ Contexte après (50 caractères)")
    logger.info("   ✅ ID/nom si disponible dans le marker")
    logger.info("=" * 80)
    
    # Détection GPU centralisée
    device = check_gpu()
    
    logger.info("\n" + "=" * 80)
    logger.info(f"📂 {len(INPUT_CONFIGS)} SOURCES À TRAITER")
    logger.info("=" * 80)
    
    for i, config in enumerate(INPUT_CONFIGS, 1):
        logger.info(f"{i}. {config['name']}")
        logger.info(f"   → Input:  {config['input_dir']}")
        logger.info(f"   → Output: {config['output_dir']}")
    
    all_stats = []
    overall_start = time.time()
    
    for config in INPUT_CONFIGS:
        stats = process_directory(config, device)
        all_stats.append(stats)
    
    overall_duration = time.time() - overall_start
    
    # ========== RÉSUMÉ FINAL ==========
    logger.info("\n" + "=" * 80)
    logger.info("📊 RÉSUMÉ FINAL - CHUNKING SÉMANTIQUE AVEC TRACKING MÉDIAS")
    logger.info("=" * 80)
    
    total_files = sum(s.get('total', 0) for s in all_stats)
    total_success = sum(s.get('success', 0) for s in all_stats)
    total_chunks = sum(s.get('total_chunks', 0) for s in all_stats)
    total_tokens = sum(s.get('total_tokens', 0) for s in all_stats)
    total_images = sum(s.get('total_images', 0) for s in all_stats)
    total_tables = sum(s.get('total_tables', 0) for s in all_stats)
    total_code_blocks = sum(s.get('total_code_blocks', 0) for s in all_stats)
    
    logger.info(f"\n📈 Statistiques globales:")
    logger.info(f"   Fichiers traités: {total_success:,}/{total_files:,}")
    logger.info(f"   Chunks créés: {total_chunks:,}")
    logger.info(f"   Tokens totaux: {total_tokens:,}")
    logger.info(f"   Temps total: {overall_duration:.1f}s")
    logger.info(f"   Vitesse moyenne: {total_success/overall_duration:.2f} fichiers/s")
    
    logger.info(f"\n🎯 Détection des médias:")
    logger.info(f"   Images détectées: {total_images:,} (avec positions précises)")
    logger.info(f"   Tables détectées: {total_tables:,} (avec positions précises)")
    logger.info(f"   Code blocks: {total_code_blocks:,}")
    
    logger.info(f"\n📂 Détails par source:")
    for stats in all_stats:
        if 'error' in stats:
            logger.error(f"   ❌ {stats['name']}: ERREUR - {stats['error']}")
        else:
            logger.info(f"   ✅ {stats['name']}:")
            logger.info(f"      Fichiers: {stats['success']}/{stats['total']}")
            logger.info(f"      Chunks: {stats['total_chunks']:,}")
            logger.info(f"      Tokens: {stats['total_tokens']:,}")
            logger.info(f"      Images: {stats['total_images']:,}")
            logger.info(f"      Tables: {stats['total_tables']:,}")
            logger.info(f"      Code blocks: {stats.get('total_code_blocks', 0):,}")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ CHUNKING TERMINÉ AVEC SUCCÈS!")
    logger.info("=" * 80)
    logger.info(f"📁 Log sauvegardé: {LOG_FILE}")
    logger.info("=" * 80)
    
    # ========== EXEMPLE D'UTILISATION DES MÉTADONNÉES ==========
    logger.info("\n" + "=" * 80)
    logger.info("💡 EXEMPLE D'UTILISATION DES MÉTADONNÉES")
    logger.info("=" * 80)
    logger.info("""
Pour lire les positions des médias dans un chunk:

```python
import json
from pathlib import Path

# Charger les métadonnées d'un chunk
metadata_path = Path("output_dir/fichier_chunk_001.json")
with open(metadata_path, 'r', encoding='utf-8') as f:
    metadata = json.load(f)

# Accéder aux images avec positions précises
for img in metadata['images_detailed']:
    print(f"Image: {img['image_id']}")
    print(f"  Position absolue: {img['position']['char_absolute']}")
    print(f"  Ligne: {img['position']['line_number']}")
    print(f"  Contexte avant: {img['context']['before']}")
    print(f"  Contexte après: {img['context']['after']}")

# Accéder aux tables
for tbl in metadata['tables_detailed']:
    print(f"Table: {tbl['table_id']}")
    print(f"  Position: ligne {tbl['position']['line_number']}")
    print(f"  Contexte: {tbl['context']['before']}")

# Résumés compacts pour affichage rapide
print(f"Total images: {metadata['total_images']}")
print(f"Total tables: {metadata['total_tables']}")
print(f"Résumé images: {metadata['image_summary']}")
```
    """)
    logger.info("=" * 80)

if __name__ == "__main__":
    main()