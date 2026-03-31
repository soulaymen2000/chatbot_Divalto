import os
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup


class CHMToTextConverter:
    """
    Convertit des fichiers .chm en texte propre en passant par HTML
    """
    
    def __init__(self, chm_folder, output_folder="output"):
        """
        Initialise le convertisseur
        
        Args:
            chm_folder: Dossier contenant les fichiers .chm
            output_folder: Dossier de sortie pour HTML et texte
        """
        self.chm_folder = chm_folder
        self.output_folder = output_folder
        self.html_folder = os.path.join(output_folder, "html")
        self.text_folder = os.path.join(output_folder, "text")
        
        # Créer les dossiers de sortie
        os.makedirs(self.html_folder, exist_ok=True)
        os.makedirs(self.text_folder, exist_ok=True)
        
        print(f"📁 Dossier CHM source: {self.chm_folder}")
        print(f"📁 Dossier HTML de sortie: {self.html_folder}")
        print(f"📁 Dossier texte de sortie: {self.text_folder}")
    
    def extract_chm_to_html(self, chm_file):
        """
        Extrait un fichier CHM en HTML
        
        Args:
            chm_file: Chemin complet vers le fichier .chm
            
        Returns:
            Chemin du dossier contenant les fichiers HTML extraits
        """
        print(f"\n🔄 Extraction de {os.path.basename(chm_file)}...")
        
        chm_name = Path(chm_file).stem
        output_dir = os.path.join(self.html_folder, chm_name)
        
        # Créer le dossier de sortie
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Méthode 1: Utiliser 7z (7-Zip)
            seven_zip_path = r"C:\Program Files\7-Zip\7z.exe"
            result = subprocess.run(
                [seven_zip_path, 'x', chm_file, f'-o{output_dir}', '-y'],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"✅ Extraction réussie dans {output_dir}")
            return output_dir
            
        except FileNotFoundError:
            print("❌ Erreur: 7z n'est pas installé")
            print("\n💡 Solutions:")
            print("   Linux: sudo apt-get install p7zip-full")
            print("   Windows: Téléchargez 7-Zip depuis https://www.7-zip.org/")
            print("   Mac: brew install p7zip")
            return None
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur lors de l'extraction: {e}")
            print(f"   Sortie: {e.stderr}")
            return None
    
    def html_to_text(self, html_file):
        """
        Convertit un fichier HTML en texte propre
        
        Args:
            html_file: Chemin vers le fichier HTML
            
        Returns:
            Texte extrait et nettoyé
        """
        try:
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Parser le HTML avec BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Supprimer les éléments inutiles
            for element in soup(["script", "style", "meta", "link"]):
                element.decompose()
            
            # Extraire le texte
            text = soup.get_text()
            
            # Nettoyer le texte
            # 1. Séparer les lignes
            lines = (line.strip() for line in text.splitlines())
            
            # 2. Diviser les lignes en morceaux
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            
            # 3. Joindre les morceaux non-vides
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            # 4. Supprimer les lignes vides multiples
            while '\n\n\n' in text:
                text = text.replace('\n\n\n', '\n\n')
            
            return text.strip()
            
        except Exception as e:
            print(f"⚠️  Erreur lors de la conversion de {html_file}: {e}")
            return ""
    
    def process_html_folder(self, html_folder, chm_name):
        """
        Traite tous les fichiers HTML d'un dossier en préservant la hiérarchie
        
        Args:
            html_folder: Dossier contenant les fichiers HTML
            chm_name: Nom du fichier CHM d'origine
            
        Returns:
            Liste des chemins des fichiers texte créés
        """
        text_files = []
        file_count = 0
        
        print(f"\n📝 Conversion HTML → Texte pour '{chm_name}'...")
        
        for root, dirs, files in os.walk(html_folder):
            for file in files:
                if file.endswith(('.html', '.htm', '.HTML', '.HTM')):
                    html_path = os.path.join(root, file)
                    
                    # Convertir en texte
                    text_content = self.html_to_text(html_path)
                    
                    if text_content:
                        # Calculer le chemin relatif depuis html_folder
                        relative_path = os.path.relpath(html_path, html_folder)
                        
                        # Changer l'extension en .txt
                        text_filename = os.path.splitext(relative_path)[0] + '.txt'
                        
                        # Créer le chemin complet: text_folder/chm_name/chemin_relatif
                        text_path = os.path.join(self.text_folder, chm_name, text_filename)
                        
                        # Créer tous les sous-dossiers nécessaires
                        os.makedirs(os.path.dirname(text_path), exist_ok=True)
                        
                        # Sauvegarder le fichier texte
                        with open(text_path, 'w', encoding='utf-8') as f:
                            f.write(text_content)
                        
                        text_files.append(text_path)
                        file_count += 1
                        
                        # Afficher la progression tous les 10 fichiers
                        if file_count % 10 == 0:
                            print(f"   ⏳ {file_count} fichiers traités...")
        
        print(f"✅ {file_count} fichiers texte créés pour '{chm_name}'")
        return text_files
    
    def convert_all_chm_files(self):
        """
        Convertit tous les fichiers CHM du dossier source
        
        Returns:
            Dictionnaire avec les statistiques de conversion
        """
        # Trouver tous les fichiers .chm
        chm_files = [f for f in os.listdir(self.chm_folder) 
                     if f.lower().endswith('.chm')]
        
        if not chm_files:
            print(f"❌ Aucun fichier .chm trouvé dans {self.chm_folder}")
            return None
        
        print(f"\n📚 {len(chm_files)} fichier(s) .chm trouvé(s)")
        
        stats = {
            'total_chm': len(chm_files),
            'success': 0,
            'failed': 0,
            'total_text_files': 0,
            'chm_processed': []
        }
        
        # Traiter chaque fichier CHM
        for i, chm_file in enumerate(chm_files, 1):
            print(f"\n{'='*60}")
            print(f"📦 [{i}/{len(chm_files)}] Traitement de: {chm_file}")
            print(f"{'='*60}")
            
            chm_path = os.path.join(self.chm_folder, chm_file)
            chm_name = Path(chm_file).stem
            
            # Étape 1: Extraire CHM → HTML
            html_dir = self.extract_chm_to_html(chm_path)
            
            if html_dir:
                # Étape 2: Convertir HTML → Texte
                text_files = self.process_html_folder(html_dir, chm_name)
                
                stats['success'] += 1
                stats['total_text_files'] += len(text_files)
                stats['chm_processed'].append({
                    'name': chm_file,
                    'text_files_count': len(text_files),
                    'status': 'success'
                })
            else:
                stats['failed'] += 1
                stats['chm_processed'].append({
                    'name': chm_file,
                    'text_files_count': 0,
                    'status': 'failed'
                })
        
        return stats
    
    def print_summary(self, stats):
        """
        Affiche un résumé des conversions
        
        Args:
            stats: Dictionnaire des statistiques
        """
        print(f"\n{'='*60}")
        print("📊 RÉSUMÉ DE LA CONVERSION")
        print(f"{'='*60}")
        print(f"✅ Fichiers CHM traités avec succès: {stats['success']}/{stats['total_chm']}")
        print(f"❌ Fichiers CHM échoués: {stats['failed']}/{stats['total_chm']}")
        print(f"📄 Total de fichiers texte créés: {stats['total_text_files']}")
        print(f"\n📁 Fichiers de sortie:")
        print(f"   HTML: {self.html_folder}")
        print(f"   Texte: {self.text_folder}")
        
        if stats['chm_processed']:
            print(f"\n📋 Détails par fichier:")
            for item in stats['chm_processed']:
                status_icon = "✅" if item['status'] == 'success' else "❌"
                print(f"   {status_icon} {item['name']}: {item['text_files_count']} fichiers texte")


# =========================
# FONCTION PRINCIPALE
# =========================
def main():
    """
    Point d'entrée principal du programme
    """
    print("="*60)
    print("🔄 CONVERSION CHM → HTML → TEXTE")
    print("="*60)
    
    # Configuration
    CHM_FOLDER = r"D:\pfe2026\data\DC\donnerCodage\CHM"
    OUTPUT_FOLDER = r"D:\pfe2026\data\CHM_EXTRACTED"
    
    # Vérifier que le dossier source existe
    if not os.path.exists(CHM_FOLDER):
        print(f"\n❌ Erreur: Le dossier '{CHM_FOLDER}' n'existe pas")
        print("\n💡 Modifiez la variable CHM_FOLDER avec le bon chemin")
        return
    
    # Créer le convertisseur
    converter = CHMToTextConverter(CHM_FOLDER, OUTPUT_FOLDER)
    
    # Convertir tous les fichiers
    stats = converter.convert_all_chm_files()
    
    # Afficher le résumé
    if stats:
        converter.print_summary(stats)
        print(f"\n{'='*60}")
        print("✨ Conversion terminée !")
        print(f"{'='*60}")
    else:
        print("\n❌ Aucune conversion effectuée")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    main()