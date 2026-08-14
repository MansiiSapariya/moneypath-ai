
# MoneyPath AI

> A multilingual AI-powered financial guidance platform that combines personal finance analytics, government scheme recommendations, financial literacy, and conversational assistance.

## Overview

MoneyPath AI is a web-based financial guidance platform designed to make personal finance information easier to understand and more accessible.

The application combines:

- Personal financial profile management
- Income and expense tracking
- Financial analytics
- Financial goals
- Government welfare scheme recommendations
- Semantic matching
- Multilingual interaction
- Voice-enabled assistance
- Financial literacy content
- AI-powered conversational guidance

The project is built as an end-to-end application using **Flask, PostgreSQL, Firebase Authentication, machine learning, NLP, and web technologies**.

> **Note:** MoneyPath AI is a prototype and educational decision-support system. It is not a banking application and does not provide regulated financial advice.

---

## Problem

Financial information can be difficult to understand because it is often:

- Fragmented across different sources
- Written in technical language
- Difficult to personalize
- Difficult to navigate for users with limited financial literacy
- Difficult to connect with relevant government schemes

MoneyPath AI attempts to address these challenges by combining financial information, user context, analytics, and recommendation capabilities into one platform.

---

## Key Features

### Personal Financial Management

Users can maintain information related to:

- Income
- Expenses
- Transactions
- Savings
- Loans
- Financial goals

The application uses this information to generate personalized financial insights.

---

### Financial Analytics

The platform calculates and presents financial indicators such as:

- Savings rate
- Expense ratio
- Expense distribution
- Financial health indicators
- Goal progress
- Potential overspending
- Financial risk signals

These metrics are presented through the application's dashboard to help users understand their financial situation.

---

### Government Scheme Recommendation

One of the main components of MoneyPath AI is its personalized government-scheme recommendation system.

The system combines:

1. **Strict eligibility filtering**
2. **Soft eligibility matching**
3. **Semantic similarity**

The recommendation pipeline can be represented as:

```text
User Profile
     |
     v
Eligibility Filtering
     |
     v
Candidate Government Schemes
     |
     v
Semantic Similarity
     |
     v
Personalized Ranking
     |
     v
Recommended Schemes
````

Eligibility can consider attributes such as:

* State
* Age
* Gender
* Occupation
* Income
* Social category
* Disability status
* Marital status

For semantic matching, scheme information is converted into embeddings using the:

```text
all-MiniLM-L6-v2
```

sentence-transformer model.

Cosine similarity is then used to measure the semantic relationship between the user's context and available schemes.

---

## AI-Assisted Financial Guidance

The application includes a conversational interface designed to provide financial education and contextual guidance.

The assistant can use information such as:

* User profile
* Financial metrics
* Recommended schemes
* Financial literacy content

The interface also supports voice interaction.

---

## Multilingual Support

MoneyPath AI is designed with Hindi and English interaction in mind.

Multilingual functionality is incorporated into:

* User onboarding
* Financial literacy content
* Conversational interaction
* Voice-based interaction

This is intended to make financial information more accessible to users who may prefer interacting in Hindi rather than English.

---

## Financial Literacy Hub

The application includes a dedicated learning section containing educational financial content.

Topics include areas such as:

* Budgeting
* Saving
* Financial planning
* Basic personal finance concepts
* The 50/30/20 budgeting framework

The repository includes the financial literacy content used by the prototype.

---

## Authentication

Firebase Authentication is used for phone-based OTP authentication.

The general authentication flow is:

```text
User
  |
  v
Phone Number
  |
  v
Firebase OTP Verification
  |
  v
Firebase ID Token
  |
  v
Flask Backend
  |
  v
Application User
```

Firebase Admin SDK is used by the backend to verify authentication tokens.

---

## System Architecture

MoneyPath AI follows a layered web application architecture:

```text
                         USER
                           |
                           v
              HTML / Tailwind / JavaScript
                           |
                           v
                    Flask Application
                           |
          ┌────────────────┼────────────────┐
          |                |                |
          v                v                v
   Authentication      Analytics      Recommendation
          |                |                |
      Firebase         Financial       Eligibility +
                       Metrics         Semantic Search
          |                |                |
          └────────────────┼────────────────┘
                           |
                           v
                      PostgreSQL
```

The application separates:

* Frontend presentation
* Backend application logic
* Authentication
* Database persistence
* Financial analytics
* Recommendation logic
* AI/NLP functionality

A simplified architecture description is available in:

```text
docs/architecture.md
```

---

## Technology Stack

### Backend

* Python
* Flask
* Flask-SQLAlchemy
* PostgreSQL
* Firebase Admin SDK

### Frontend

* HTML5
* JavaScript
* Tailwind CSS
* Firebase Authentication

### Machine Learning / NLP

* Sentence Transformers
* Scikit-learn
* NumPy
* Pandas
* Statsmodels
* TensorFlow

### Voice

* gTTS
* pyttsx3

---

## Project Structure

```text
moneypath-ai/
│
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── requirements.txt
├── package.json
├── package-lock.json
│
├── app.py
├── database.py
├── schemes.json
├── Literacy Content RBI.txt
│
├── docs/
│   └── architecture.md
│
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── login.html
│   ├── auth.html
│   ├── onboarding.html
│   ├── onboarding_user.html
│   ├── onboarding_transactions.html
│   ├── onboarding_goals.html
│   ├── dashboard.html
│   ├── transactions.html
│   ├── profile.html
│   ├── chatbot.html
│   ├── learning_hub.html
│   ├── scheme_detail.html
│   └── not_found.html
│
├── static/
│   ├── css/
│   │   └── index.css
│   ├── js/
│   │   ├── scripts.js
│   │   └── onboarding.js
│   └── images/
│
└── utils/
    └── utils.py
```

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/MansiiSapariya/moneypath-ai.git
cd moneypath-ai
```

## 2. Create a virtual environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Configuration

The repository does **not** contain database passwords or Firebase credentials.

Create a local `.env` file based on:

```text
.env.example
```

Example:

```env
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres

FIREBASE_CREDENTIALS=secrets/firebase-service-account.json
```

### Important

Never commit:

```text
.env
firebase-service-account.json
```

or any other private credentials.

The `.gitignore` file is configured to prevent common credential and environment files from being committed.

---

# Firebase Setup

Create a Firebase project and enable phone authentication.

Then create a Firebase Admin service account and store the credentials locally.

For example:

```text
secrets/
└── firebase-service-account.json
```

Set the path in `.env`:

```env
FIREBASE_CREDENTIALS=secrets/firebase-service-account.json
```

The credential file should remain local and should **never be pushed to GitHub**.

---

# PostgreSQL Setup

Create a PostgreSQL database and configure the connection through environment variables.

Example:

```env
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
```

The application reads these values at runtime rather than storing credentials directly in the source code.

---

# Initialize the Database

Run:

```bash
python database.py
```

This initializes the database structures required by the application.

---

# Run the Application

Start the Flask application:

```bash
python app.py
```

The application can then be accessed through the local Flask server.

---

# Recommendation System

The recommendation engine is designed as a hybrid system rather than relying solely on semantic similarity.

## Step 1 — User Profile

The system obtains relevant user information such as:

```text
Age
State
Income
Occupation
Gender
Social Category
Disability
Marital Status
```

## Step 2 — Eligibility Filtering

Strict eligibility constraints are checked where they are available in the scheme data.

For example:

```text
State
Age Range
Income Limits
Occupation
Gender
Category
Disability
Marital Status
```

## Step 3 — Semantic Representation

Government scheme information is transformed into vector representations using:

```text
all-MiniLM-L6-v2
```

## Step 4 — Similarity

Cosine similarity is used to compare relevant text representations.

## Step 5 — Recommendation

The system produces a set of schemes that are relevant to the user's profile and context.

This approach attempts to combine:

```text
Rule-Based Eligibility
          +
Semantic Relevance
          +
User Context
          ↓
Personalized Recommendations
```

---

# Application Flow

A typical user journey is:

```text
Landing Page
     |
     v
Authentication
     |
     v
Onboarding
     |
     ├── Personal Information
     ├── Financial Information
     ├── Transactions
     └── Financial Goals
     |
     v
Dashboard
     |
     ├── Financial Analytics
     ├── Financial Health
     ├── Goals
     ├── Transactions
     └── Recommendations
              |
              v
       Government Schemes
              |
              v
         AI Guidance
              |
              v
      Financial Literacy
```

---

# Security

Sensitive configuration is intentionally kept outside the repository.

Do not commit:

* Database passwords
* Firebase service-account credentials
* API keys
* Private keys
* `.env` files
* Production credentials
* Personal financial information

The repository uses environment variables for database configuration.

---

# Limitations

MoneyPath AI is a prototype and has several limitations:

* It is not integrated with live banking systems.
* It does not execute financial transactions.
* Government scheme information may change over time.
* Scheme recommendations depend on the quality and completeness of the available scheme data.
* The recommendation system has not been validated through large-scale real-world deployment.
* Voice and multilingual functionality may vary depending on language and environment.
* Production-scale load and performance testing has not been established.
* The application should not be treated as a substitute for professional financial advice.

---

# Future Scope

Potential improvements include:

### Financial Intelligence

* Expense forecasting
* Cash-flow forecasting
* Personalized savings recommendations
* Financial goal prediction
* Anomaly detection
* More advanced financial health scoring

### Recommendation System

* Learning-to-rank recommendations
* Feedback-based recommendation refinement
* Personalized recommendation ranking
* Real-time government scheme data
* Government API integration

### AI Assistant

* Improved multilingual models
* Retrieval-Augmented Generation (RAG)
* More explainable responses
* Personalized financial education
* Context-aware financial planning

### Platform

* Mobile application
* Additional Indian languages
* Improved speech recognition
* Offline capabilities
* Automated testing
* Production deployment
* Performance and load testing

---

# What This Project Demonstrates

This project demonstrates practical experience across multiple areas of software and AI development:

```text
                 MoneyPath AI
                     |
       ┌─────────────┼─────────────┐
       |             |             |
   Full Stack       Data          AI/NLP
       |             |             |
    Flask        Analytics     Embeddings
    PostgreSQL   Financial     Semantic Search
    Firebase     Metrics       Recommendations
    JavaScript   Insights      Chatbot
       |             |             |
       └─────────────┼─────────────┘
                     |
              End-to-End AI
                 Application
```

Key technical areas include:

* Full-stack application development
* REST-style Flask routing
* PostgreSQL database integration
* Firebase authentication
* Financial data processing
* Machine learning
* NLP and semantic similarity
* Recommendation systems
* Multilingual interaction
* Voice interfaces
* AI-assisted decision support

---

# Disclaimer

MoneyPath AI is an educational and research-oriented prototype.

The system does not provide regulated financial advice, guarantee government-scheme eligibility, or execute financial transactions.

Government scheme information and financial recommendations should be independently verified through official sources before making financial decisions.

---

# Author

**Mansi Sapariya**

MSc Data Science




Also, the cleaned ZIP you have now already uses environment variables for `DB_PASSWORD`, so the README's security/setup instructions match the code in the repository.
```
