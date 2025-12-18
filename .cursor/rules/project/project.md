# **Healthcare Data Processing API**

## **Overview**

This is a backend application that processes healthcare data using modern API development practices. The project is broken into 4 parts: backend foundation, patient note handling, summary generation, and containerization & deployment.

The goal is to create a robust API for managing and processing medical documents. For testing, we have provided sample medical notes in SOAP format (Subjective, Objective, Assessment, and Plan).

**THUMBSTONE RULE**: The project is avaluated based on:

- Correctness and completeness of each part
- Code quality and employing best practices in software development with Python
- Documentation and ease of local setup
- API design and error handling
- Performance considerations
- Testing approach

---

## **Part 1: FastAPI Backend Foundation**

Set up a backend service using FastAPI and a relational database to provide a RESTful JSON API for storing and retrieving patient medical records.

**Tasks:**

1. Initialize a FastAPI application with a health-check endpoint (`GET /health`) that returns `{"status": "ok"}`.
2. Set up a database with a schema for storing patient records. At minimum, include a way to store `patients` along with a unique identifier, name, and data of birth.
    1. Please ensure it’s possible for another developer to recreate this database easily..
3. Implement CRUD endpoints for managing patients:
    - `GET /patients` - List all patients, including paging
    - `GET /patients/{id}` - Get a specific patient
    - `POST /patients` - Create a new patient
    - `PUT /patients/{id}` - Update a patient
    - `DELETE /patients/{id}` - Delete a patient
4. Implement proper error handling and input validation.
5. Document the API in the repository as you see fit  It should be easy for others to understand how the API behaves without having to look at the code.

For this, Let's use Postgree as database. Let's use docker/docker compose to handle python fast api server and postgre DB.

**Input/Output Expectations:**

- **Input:** HTTP requests to your FastAPI server
- **Output:** JSON responses with appropriate status codes

**Stretch Goals:**

- Add sorting on the list endpoint that will be respected when paging
- Implement filtering on the `GET /patients` endpoint (e.g. a fuzzy search)
- Implement proper logging middleware

---

## **Part 2: Extend the API to Accept Patient Notes**

Add endpoints to add simple notes about a patient. You may assume these are short blurbs of plain text, and accept them either as a file upload or part of the request body.

**Tasks:**

1. Create an endpoint to upload notes related to a patient.
    
    The endpoint should accept a timestamp indicating when the note was taken as well as its actual contents.
    
2. Create an endpoint to view all patients notes.
3. Create an endpoint to delete patient notes.

Note: you do not need to worry about updating notes, as it’s sufficient to delete and re-upload a note.

**Input/Output Expectations:**

- Patient notes will be short notes written by a healthcare professional collected during admission, patient check-ins, or doctor visits. They maybe written in the SOAP format described at the end of this document.

For simplicity, you may imagine that these notes track a patient as they are admitted into a hospital (e.g. chief complaints, family history, medical observations, medications) and then routine check-ins by caretakers to evaluate their progress all the way up to a discharge note.

**Stretch Goals:**

- Allow notes to be more than just text files, such as PDFs or handwritten notes.
- Classify the type of note being taken.
- Collect any structured data about the patient.

---

## **Part 3: Patient Summary Generation**

Add an endpoint to generate a concise patient summary based on their profile in database and the collection of notes collected in the previous step.

**Tasks:**

1. Create an endpoint (`GET /patients/{id}/summary`) that provides a summary of the patient using their notes.
2. Synthesize a human-readable summary that includes:
    - A heading with basic patient identifiers (e.g., name, age, MRN)
    - A coherent narrative generated from the provided notes
3. Ensure the summary clearly communicates key clinical information (e.g., diagnoses, medications, observations).

This summary is intended to give a quick, accurate picture of the patient’s condition to a care team member reviewing the case.

Let's integrate with OpenAPI API and generate a prompt with pacient info to get back from the API a ChatGPT summary.

**Input/Output Expectations:**

- **Input:** Patient metadata and medical notes provided through the endpoints created in the first 2 parts.
- **Output:** Structured JSON including patient heading and summary text

**Stretch Goals:**

- Allow customization of summary. This is up to you—but some ideas might include tailoring it towards a specific audience (family v.s. other clinicians) or length / verbosity.

---

## **Part 4: Containerization and Deployment**

Containerize your application and set up a complete local development environment.

**Tasks:**

1. Create a `Dockerfile` for your application using an appropriate Python base image.
2. Create a `docker-compose.yml` that includes:
    - Your FastAPI application
    - The database service
    - Any other required services
3. Configure environment variables properly using `.env` files (include an example `.env.example`).
4. Write scripts to initialize the database with sample data on startup.
5. Include detailed documentation on how to build, run, and test the containerized application.

**Stretch Goals:**

- Set up different configurations for development and production
- Create a CI pipeline configuration file (e.g., GitHub Actions)
- Add monitoring capabilities (e.g., Prometheus metrics)
- Use a local Kubernetes setup instead of `docker compose`.
- Automated testing using Github runners.

## **Architectural Rules**
Let's use vertical slice architecture over the project


## **Documentation**
During the project, document each step of development (milestones) in ProjectHistory.md on the root of the project.