# FundFlow AI

**Autonomous Career Intelligence Agent**

FundFlow AI discovers newly funded startups, researches them, matches them with your resume, and generates personalized application materials automatically.

---

## Project Overview

FundFlow AI is an AI-powered career intelligence platform that automates the job search process by:

- **Weekly Discovery**: Automatically discovers startups funded in the last 7 days
- **AI Research**: Deep research on company tech stack, business model, and hiring signals
- **Smart Matching**: AI-powered matching based on skills, experience, and industry fit
- **Auto Generation**: Generates personalized cover letters and application materials

---

## Architecture

### Tech Stack

**Backend**
- FastAPI - Modern, fast web framework for building APIs
- SQLAlchemy - SQL toolkit and ORM
- SQLite - Lightweight database
- Pydantic - Data validation using Python type annotations
- PyMuPDF (fitz) - PDF text extraction (primary)
- pdfplumber - PDF text extraction (fallback)
- OpenAI SDK - LLM analysis with structured output

**Frontend**
- React - UI library
- Vite - Next generation frontend tooling
- TailwindCSS - Utility-first CSS framework
- React Router - Declarative routing for React
- Axios - HTTP client

### High-Level Architecture

```
Frontend (React + TailwindCSS)
    ↓ HTTP/REST
Backend API (FastAPI)
    ↓
PDF Extraction (PyMuPDF/pdfplumber)
    ↓
LLM Analysis (OpenAI gpt-4.1-mini)
    ↓
Database (SQLite)
```

### Resume Upload Flow

```
User uploads PDF
    ↓
Validate file type & size (max 10MB)
    ↓
Extract text using PyMuPDF
    ↓ (fallback if needed)
Extract text using pdfplumber
    ↓
Send to OpenAI gpt-4.1-mini
    ↓
Receive structured JSON analysis
    ↓
Store in SQLite database
    ↓
Display analysis in Linear-style UI
```

---

## Folder Structure

```
Pratik_Assignment/
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example           # Environment variables template
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/         # API route handlers
│   │   │       ├── health.py   # Health check endpoint
│   │   │       ├── resume.py   # Resume endpoints
│   │   │       ├── companies.py # Company endpoints
│   │   │       ├── matches.py  # Match endpoints
│   │   │       └── documents.py # Document generation endpoints
│   │   ├── core/
│   │   │   ├── config.py      # Configuration settings
│   │   │   └── logging.py     # Logging configuration
│   │   ├── db/
│   │   │   └── session.py     # Database session management
│   │   ├── models/            # SQLAlchemy models
│   │   │   ├── company.py
│   │   │   ├── resume.py
│   │   │   ├── match.py
│   │   │   └── generated_document.py
│   │   ├── schemas/           # Pydantic schemas
│   │   │   ├── company.py
│   │   │   ├── resume.py
│   │   │   ├── match.py
│   │   │   └── document.py
│   │   ├── services/          # Business logic services
│   │   │   ├── company_service.py
│   │   │   ├── resume_service.py
│   │   │   ├── match_service.py
│   │   │   └── generation_service.py
│   │   ├── agents/            # AI agents (Future Milestones)
│   │   │   ├── coordinator.py
│   │   │   ├── discovery.py
│   │   │   ├── research.py
│   │   │   ├── matching.py
│   │   │   └── generation.py
│   │   ├── tools/             # Agent tools (Future Milestones)
│   │   │   ├── web_scraper.py
│   │   │   └── document_parser.py
│   │   └── utils/             # Utility functions
│   │       └── helpers.py
│
├── frontend/
│   ├── package.json           # Node dependencies
│   ├── vite.config.js         # Vite configuration
│   ├── tailwind.config.js     # TailwindCSS configuration
│   ├── index.html             # HTML entry point
│   ├── .env.example          # Environment variables template
│   └── src/
│       ├── main.jsx           # React entry point
│       ├── App.jsx            # Main app component
│       ├── index.css          # Global styles
│       ├── components/        # Reusable components
│       │   ├── Button.jsx
│       │   ├── Card.jsx
│       │   ├── Loader.jsx
│       │   ├── Navbar.jsx
│       │   └── Sidebar.jsx
│       ├── layouts/           # Layout components
│       │   └── Layout.jsx
│       ├── pages/             # Page components
│       │   ├── Landing.jsx
│       │   ├── Dashboard.jsx
│       │   ├── ResumeUpload.jsx
│       │   └── CompanyDetails.jsx
│       ├── services/          # API services
│       │   ├── api.js
│       │   ├── resumeService.js
│       │   ├── companyService.js
│       │   ├── matchService.js
│       │   └── generationService.js
│       ├── hooks/             # Custom React hooks
│       │   └── index.js
│       └── utils/             # Utility functions
│           └── index.js
│
└── README.md                  # This file
```

---

## Setup

### Prerequisites

- Python 3.8+
- Node.js 16+
- npm or yarn

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Create environment file:
```bash
cp .env.example .env
```

6. **Important**: Set your OpenAI API key in the `.env` file:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

7. Run the backend:
```bash
python main.py
```

The backend will start on `http://localhost:8000`

API documentation available at `http://localhost:8000/docs`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create environment file:
```bash
cp .env.example .env
```

4. Run the frontend:
```bash
npm run dev
```

The frontend will start on `http://localhost:3000`

---

## Current Milestone (Milestone 2)

**Status**: ✅ Complete

**Implemented**:
- ✅ All Milestone 1 features
- ✅ Resume upload endpoint (`POST /api/resume/upload`)
- ✅ PDF text extraction with PyMuPDF (primary) and pdfplumber (fallback)
- ✅ LLM analysis service using OpenAI Responses API with structured output
- ✅ Resume model updated to store full analysis JSON
- ✅ Pydantic schemas for resume analysis response
- ✅ Linear-style minimal UI for resume upload page
- ✅ Beautiful analysis display with:
  - Skills chips (primary color)
  - Technologies badges (purple color)
  - Experience timeline
  - Education list
  - Projects and certifications
  - Strengths grid
- ✅ Loading states with progress stages (uploading → extracting → analyzing → saving)
- ✅ Comprehensive error handling (file type, size, extraction, LLM errors)
- ✅ Security features (file size limit, MIME type validation, temp file cleanup)
- ✅ OpenAI API key configuration

**Resume Upload Flow**:
1. User uploads PDF file (drag & drop or click)
2. Backend validates file type and size (max 10MB)
3. PDF text extraction using PyMuPDF with pdfplumber fallback
4. LLM analysis using OpenAI gpt-4.1-mini with structured JSON output
5. Store analysis in SQLite database
6. Display beautiful analysis results in Linear-style UI

**Testing**:
- ✅ Health endpoint: `GET /api/health`
- ✅ Resume upload: `POST /api/resume/upload`
- ✅ Frontend navigation between pages
- ✅ Dark mode UI
- ✅ Resume analysis display

---

## Future Milestones

### Milestone 3: Company Discovery
- Implement web scraping tools
- Discovery Agent for finding funded companies
- Company research from external sources
- Store company data in database
- Display companies in dashboard

### Milestone 4: Company Research
- Deep research on discovered companies
- Extract tech stack from websites
- Identify business model and hiring signals
- Enrich company profiles

### Milestone 5: AI Matching & Ranking
- Implement Matching Agent
- Calculate match scores based on skills and experience
- Rank companies by match score
- Display ranked matches in dashboard

### Milestone 6: Document Generation
- Implement Generation Agent
- Generate personalized cover letters
- Generate ATS-optimized resumes
- Download functionality

---

## API Endpoints

### Implemented (Milestone 2)

- `GET /api/health` - Health check endpoint
- `POST /api/resume/upload` - Upload and analyze resume PDF

### Placeholder Endpoints (Return HTTP 501)

**Companies**
- `POST /api/companies/discover` - Discover newly funded companies
- `POST /api/companies/match` - Match companies with user resume
- `GET /api/companies` - Get list of companies

**Matches**
- `GET /api/matches` - Get ranked matches for user

**Documents**
- `POST /api/documents/generate` - Generate application document

---

## Database Schema

### Companies
- id, name, description, website
- funding_amount, funding_date, funding_round
- sector, tech_stack, business_model
- team_size, stage, hiring_signals
- discovered_at, researched_at

### Resume
- id, original_filename, file_path
- Personal: name, email, phone, location
- Analysis: summary, skills, experience, education, projects, certifications, technologies, strengths
- analysis_json (full LLM response)
- raw_text (extracted PDF text)
- parsed_at

### Matches
- id, company_id, resume_id
- match_score, skill_alignment_score
- experience_relevance_score, industry_fit_score
- stage_match_score, reasoning, rank
- matched_at

### GeneratedDocuments
- id, match_id, company_id
- document_type, content
- prompt_used, model_used
- generated_at

---

## Development Notes

### Code Quality
- PEP8 compliant Python code
- Type hints throughout
- Docstrings for all functions
- Clean naming conventions
- No duplicate code

### Design Principles
- Clean architecture with separation of concerns
- Modular components for easy testing
- Scalable foundation for future enhancements
- Production-quality code structure

---

## License

This project is created as an assignment for a Generative AI Engineer Internship.

---

## Contact

For questions or feedback, please refer to the project documentation or contact the development team.
