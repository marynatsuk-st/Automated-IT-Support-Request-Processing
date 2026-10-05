# Automated IT Support Request Processing & Task Routing System

An end-to-end intelligent web application designed to automate support request workflows for IT service desks. The system incorporates a two-level hierarchical Natural Language Processing (NLP) classification pipeline to filter non-IT noise and categorize IT requests, combined with a dynamic routing algorithm that assigns tasks based on worker skill competencies and current workload.

---

## Project Objectives

* **Process Automation:** Accelerate support ticket processing and resolution speed through partial automation of service workflows using modern text analysis algorithms.
* **Hierarchical Classification:** Build a two-stage NLP model to filter out irrelevant/OOD (Out-of-Domain) messages and classify IT issues into specific service categories.
* **Automated Dispatching:** Develop a workload-balanced routing algorithm that assigns incoming tickets based on staff expertise and capacity.
* **Web Integration:** Integrate the NLP pipeline and dynamic dispatcher into a unified web service portal.

---

## 🧠 NLP Pipeline & Machine Learning Models

### Stage 1: Binary Classifier (Noise & Relevance Filtering)
* **Goal:** Distinguish relevant IT requests from irrelevant non-IT messages (e.g., HR queries, general chit-chat, news) to eliminate non-target noise before downstream processing.
* **Base Architecture:** `distilbert-base-multilingual-cased`
* **Training Setup:**
  * **Dataset Size:** 1,000 total records (500 unique IT requests + 500 non-IT messages).
  * **Split:** 80% Training (800 records), 20% Validation (200 records) using stratified splitting.
  * **Hyperparameters:** Batch size = 16, Epochs = 15, Optimizer = Adam, Loss function = `CrossEntropyLoss`.
  * **Regularization:** Early stopping with patience = 2 based on `eval_f1_macro` (`load_best_model_at_end=True`).
* **Performance:**
  * **Accuracy:** 0.96
  * **F1-Score (Macro):** 0.9714 (Best checkpoint saved at Epoch 2 via Early Stopping)

### Stage 2: Multi-Class Classifier (IT Task Category Identification)
* **Goal:** Assign relevant IT requests into one of 7 specific operational support categories.
* **Target Categories:**
  1. `Password Issues`
  2. `Security Incidents`
  3. `File and Storage management`
  4. `Application management`
  5. `Account management`
  6. `Software management`
  7. `Network management`
* **Base Architecture:** `distilbert-base-multilingual-cased`
* **Training Setup:**
  * **Dataset Size:** 2,842 augmented examples across 7 categories.
  * **Hyperparameters:** Batch size = 16, Epochs = 15, Optimizer = Adam, Loss function = `CrossEntropyLoss`.
  * **Regularization:** Early stopping with patience = 2 based on `eval_f1_macro`.
* **Evaluation & Results (Independent Test Set of 300 Unbalanced IT Requests):**
  * **Accuracy:** 0.966
  * **F1-Score (Weighted):** 0.966
  * **F1-Score (Macro):** 0.974
  * *Note:* The model demonstrated strong generalization across imbalanced test data. Minor semantic overlap occurred between *Application Management* and *Software Management*.

---

##  Database Schema & Entities

The system relies on a relational database architecture designed to manage users, roles, support requests, and competency mappings:

![Database Diagram](./assets/db_schema.png) <!-- Update image path as needed -->

### Key Entities:
* **Users / Accounts:** Stores credentials, user profiles, and assigned roles (`Worker`, `Manager`, `Client`).
* **Tasks / Tickets:** Stores incoming request metadata, extracted summary, classified category ID, urgency priority, and current status (`Pending`, `Assigned`, `In Progress`, `Resolved`, `Escalated`).
* **Worker Competencies:** Join entity mapping support personnel to specific task categories alongside an assigned expertise metric.
* **Workload Limits:** Tracks max concurrent task capacity per worker.

---

## Automated Workload Allocation Algorithm

Once a request is classified, the system dynamically routes the task using a rule-based optimization engine:

![BPMN Workflow Diagram](./assets/bpmn_workflow.png) <!-- Update image path as needed -->

### Workflow Logic:
1. **Candidate Pool Selection:** Queries active personnel with the `Worker` role matching the designated task competence.
2. **Suitability Score Calculation:** Calculates an integral fitness score for candidates based on expertise level and current active workload:
   $$\text{Score} = \text{Expertise Level} - \text{Current Active Workload}$$
3. **Capacity Threshold Enforcement:**
   * Candidates exceeding individual max capacity limits are excluded for low-priority tasks.
   * High-priority/critical incidents bypass workload limits to ensure swift dispatch.
4. **Selection & Escalation:**
   * Assigns task to candidate with the highest integral score (random selection breaks ties for load balancing).
   * **Escalation Mechanism:** If no valid candidates are available (e.g., all overloaded or offline), the ticket automatically escalates to an active `Manager` for manual handling.

---

## Data Engineering & Augmentation Strategy

1. **Deduplication & Data Leakage Prevention:**
   * Filtered identical entries from initial raw data, retaining 1,426 unique IT requests.
   * Identified and removed 190 overlapping entries between training and test sets to guarantee valid model evaluation.
   * Removed records with missing text payloads or labels.
2. **Domain-Specific Text Normalization:**
   * Built a targeted lookup dictionary replacing domain jargon, common abbreviations, and typos with canonical standard forms across Ukrainian-language text.
3. **Data Augmentation (Back-Translation):**
   * Doubled training samples using Helsinki-NLP models (`opus-mt`).
   * Translated text: Ukrainian $\to$ English $\to$ Ukrainian to expand vocabulary diversity while preserving core semantic meaning.
4. **Text Corpus Characteristics:**
   * Request length ranged from 51 to 371 characters (Average: ~230 characters).

---

## 🛠️ Tech Stack & Requirements

* **Language:** Python 3.8+
* **NLP & Deep Learning:** Hugging Face `transformers`, PyTorch, Scikit-learn
* **Machine Translation:** Helsinki-NLP models (`opus-mt`)
* **Web Framework & Database:** Python (FastAPI / Flask / Django), SQL Database
* **Data Processing:** Pandas, NumPy