# **Divalto Tableau Data Extraction & Chatbot Framework**

![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Stars](https://img.shields.io/github/stars/yourusername/chatbot_Divalto?style=social)

---

## 🚀 **Overview**

**Divalto Tableau Data Extraction** is a **Python-based data processing pipeline** designed to extract, clean, and transform structured data from **Tableau-compatible formats** (HTML, MHTML, CSV, etc.). This project includes:

✅ **Robust HTML/XML parsing** with special character support (accents, €, ®, ™, etc.)
✅ **Automatic encoding detection** and conversion to UTF-8
✅ **Advanced text cleaning** (removing HTML entities, normalizing whitespace, etc.)
✅ **CSV generation with BOM** for seamless Excel compatibility
✅ **Hierarchy preservation** in extracted data

**Divalto Chatbot** is a **React-based frontend** integrated with this backend, providing a **user-friendly interface** for:
💬 **Interactive chatbot** for data exploration
📊 **Visualization of extracted data**
🔍 **Search and filter capabilities**

This project is ideal for **data analysts, developers, and businesses** needing to **extract, process, and visualize structured data** efficiently.

---

## ✨ **Features**

### **Data Extraction Engine**
- **Multi-format support**: HTML, MHTML, CSV, and more
- **Special character handling**: Full Unicode support (accents, symbols, etc.)
- **HTML entity decoding**: Converts `&eacute;` → `é`, `&nbsp;` → space
- **Encoding detection**: Automatically detects and converts encodings
- **CSV generation**: Creates UTF-8 CSV files with BOM for Excel compatibility

### **Chatbot Interface**
- **React-based frontend** with **TypeScript** for type safety
- **Interactive chat UI** with **shadcn/ui** components
- **Data visualization** with **Chart.js** or **D3.js**
- **Search & filter** capabilities for extracted data
- **Responsive design** for all devices

### **Technical Highlights**
- **Python 3.8+** with **BeautifulSoup, chardet, and logging** for robust processing
- **React 18+** with **Vite** for fast frontend builds
- **Modular architecture** for easy extension
- **Docker support** for seamless deployment

---

## 🛠️ **Tech Stack**

| Category          | Technologies Used                                                                 |
|-------------------|----------------------------------------------------------------------------------|
| **Backend**       | Python 3.8+, BeautifulSoup, chardet, logging, pandas (optional)                   |
| **Frontend**      | React 18+, TypeScript, Vite, shadcn/ui, Tailwind CSS                            |
| **Data Processing** | CSV, UTF-8, BOM, HTML/XML parsing                                                 |
| **Deployment**    | Docker, Node.js, Python virtual environments                                      |
| **Testing**       | pytest (backend), Jest/React Testing Library (frontend)                           |

---

## 📦 **Installation**

### **Prerequisites**
- **Python 3.8+** ([Download Python](https://www.python.org/downloads/))
- **Node.js 18+** ([Download Node.js](https://nodejs.org/))
- **Git** ([Download Git](https://git-scm.com/downloads))
- **Docker** (optional, for containerized deployment)

---

### **Quick Start (Backend)**

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/chatbot_Divalto.git
   cd chatbot_Divalto
   ```

2. **Set up a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the extraction script**:
   ```bash
   python data/extract_index_tableau.py
   ```
   - This will process files in `data/INPUT_DIR` and generate CSVs in `data/OUTPUT_DIR`.

---

### **Quick Start (Frontend)**

1. **Navigate to the frontend directory**:
   ```bash
   cd dev/NovaMind/app
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```
   - The app will be available at `http://localhost:5173`.

---

### **Alternative: Docker Setup**

1. **Build and run the Docker container**:
   ```bash
   docker-compose up --build
   ```
   - This will start both the backend and frontend services.

2. **Access the frontend**:
   - Open `http://localhost:3000` (or the port specified in `docker-compose.yml`).

---

## 🎯 **Usage**

### **Basic Data Extraction**
The `extract_index_tableau.py` script processes HTML/HTML files and generates clean CSV outputs. Example:

```python
from data.extract_index_tableau import clean_text_advanced

# Example usage
dirty_text = "<div>Hello &eacute;world! &nbsp; &copy; 2023</div>"
clean_text = clean_text_advanced(dirty_text)
print(clean_text)  # Output: "Hello éworld! © 2023"
```

### **Frontend Chatbot**
The React app provides a **chat interface** to interact with extracted data. Features include:
- **Search** extracted tables by keywords
- **Filter** data dynamically
- **Visualize** results with charts



---

### **Configuration**
- **Backend**:
  - Configure `INPUT_DIR` and `OUTPUT_DIR` in `extract_index_tableau.py`.
  - Adjust `LOG_FILE` for logging output.

- **Frontend**:
  - Environment variables (`VITE_APP_TITLE`, `VITE_APP_DESCRIPTION`) in `.env`.
  - Customize `shadcn/ui` components in `dev/NovaMind/app/components/`.

---

## 📁 **Project Structure**

```
chatbot_Divalto/
├── data/                  # Backend data processing scripts
│   ├── extract_index_tableau.py  # Main extraction script
│   └── ...                  # Other data files
├── dev/                   # Frontend application
│   ├── NovaMind/           # React app
│   │   ├── app/            # Source code
│   │   ├── public/         # Static assets
│   │   └── package.json    # Dependencies
│   └── node_modules/      # Installed frontend dependencies
├── .gitignore             # Git ignore rules
├── README.md              # This file
├── requirements.txt       # Python dependencies
└── docker-compose.yml     # Docker setup (optional)
```

---

## 🤝 **Contributing**

We welcome contributions! Here’s how you can help:

1. **Fork the repository** and clone it locally.
2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature
   ```
3. **Make your changes** and commit them:
   ```bash
   git commit -m "Add your feature description"
   ```
4. **Push to the branch**:
   ```bash
   git push origin feature/your-feature
   ```
5. **Open a Pull Request** on GitHub.

### **Development Setup**
- **Backend**: Use `venv` or `pipenv` for dependency management.
- **Frontend**: Use `npm` or `yarn` for Node.js dependencies.
- **Code Style**: Follow **PEP 8** (Python) and **ESLint** (JavaScript/TypeScript).

### **Pull Request Process**
1. Ensure your changes pass all tests.
2. Update documentation if applicable.
3. Link to related issues or features.

---

## 📝 **License**

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 👥 **Authors & Contributors**

Soulaymen Omrani
---

## 🐛 **Issues & Support**

### **Reporting Issues**
- Open an issue on GitHub with:
  - A clear description of the problem.
  - Steps to reproduce.
  - Expected vs. actual behavior.
  - Screenshots or logs (if applicable).

### **Getting Help**
- **Discussions**: Use the GitHub Discussions tab for questions.
- **Community**: Join our [Slack/Discord](link-to-community) for real-time help.
- **FAQ**: Check the [Wiki](link-to-wiki) for common questions.

---

## 🗺️ **Roadmap**

### **Planned Features**
- [ ] **Support for additional data formats** (Excel, JSON, JSON).
- [ ] **Machine learning integration** for predictive analytics.
- [ ] **Multi-language support** for the chatbot.
- [ ] **API endpoint** for programmatic data access.

### **Known Issues**
- [ ] Docker setup for Windows users (WIP).
- [ ] Performance optimization for large datasets.

### **Future Improvements**
- **User authentication** for secure data access.
- **Collaborative features** (shared workspaces).
- **Mobile app** for on-the-go data exploration.

---

## 🚀 **Get Started Today!**

Ready to extract, process, and visualize your data? **Star this repository** and contribute to the project!

```bash
git clone https://github.com/yourusername/chatbot_Divalto.git
cd chatbot_Divalto
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
npm install
npm run dev
```

**Let’s build the future of data extraction together!** 🚀
