from enum import Enum

NFR_CATEGORIES: dict[str, str] = {
    "performance":     "Performance Requirements",
    "usability":       "Usability & Accessibility Requirements",
    "security_privacy":"Security & Privacy Requirements",
    "reliability":     "Reliability Requirements",
    "compatibility":   "Compatibility & Portability Requirements",
    "maintainability": "Maintainability Requirements",
    "availability":   "Availability Requirements",
}
STRUCTURAL_CATEGORIES: dict[str, str] = {
    "purpose":"System Purpose & Goals",
    "scope":"System Scope & Boundaries",
    "stakeholders":"Stakeholders & User Classes",
    "functional":"Functional Requirements",
    "interfaces":"External Interfaces",
    "constraints":"Design & Implementation Constraints",
}
MIN_FUNCTIONAL_FOR_NFR = 10
DOMAIN_SUB_DIMENSIONS = ["data","actions","constraints","automation","edge_cases"]

# ---------------------------------------------------------------------------
# SEED PROMPT
# ---------------------------------------------------------------------------
_SEED_PROMPT = """\
You are an expert Requirements Engineer. Your colleague is conducting a \
requirements elicitation interview with a customer. Your task is to identify \
ALL FUNCTIONAL DOMAINS that a complete IEEE 830-1998 SRS for the project \
"{project_name}" must cover.

CUSTOMER'S FIRST MESSAGE:
---
{description}
---

STEP 1 — CLASSIFY THE SYSTEM TYPE.
Read the description and identify which of the following system archetypes \
best describes this project (one primary, optionally one secondary):

  MATCHING_PLATFORM   — connects two or more user groups (jobs, dating, rentals, freelance)
  MARKETPLACE         — buying/selling/trading between parties, with payments
  IOT_CONTROL         — controls physical devices, sensors, or home/building automation
  CONTENT_PLATFORM    — manages, publishes, or curates content (media, courses, news)
  ENTERPRISE_MGMT     — internal business operations (HR, ERP, CRM, project management)
  HEALTH_WELLNESS     — tracks health, fitness, medical records, or clinical workflows
  ECOMMERCE           — product catalogue, cart, checkout, fulfilment, returns
  FINANCIAL           — payments, invoicing, accounting, banking, or investment tools
  SOCIAL_NETWORK      — user-generated content, following, feeds, messaging
  EDTECH              — learning management, courses, assessments, progress tracking
  GENERAL             — does not fit the above types clearly

STEP 2 — ENUMERATE ALL FUNCTIONAL DOMAINS.
Based on the system type AND the customer's description, list every functional \
domain a complete SRS must cover. Apply these rules:

RULE A — ALWAYS include what the customer described, including anything implied \
  (e.g. "users can apply to jobs" implies both Application Submission AND \
  Application Status Tracking as separate domains).

RULE B — APPLY SYSTEM-TYPE DOMAIN TAXONOMY. For the identified type(s), \
  include ALL standard domains from the relevant list below UNLESS the customer \
  has clearly ruled them out:

  MATCHING_PLATFORM:
    Registration and Profile Management, Profile Search and Discovery,
    AI Matching and Recommendations, Match Scoring and Ranking,
    Application or Expression of Interest, Communication and Messaging,
    Review and Rating System, Saved Items and Shortlists,
    Notifications and Alerts, Subscription and Billing,
    Admin Moderation and Content Review, Analytics and Reporting Dashboard,
    External Integration and API Access, Compliance and Data Privacy Tools,
    User Account and Role Management, Help and Support Centre

  MARKETPLACE:
    Seller Registration and Listing Management, Buyer Registration and Search,
    Product or Service Catalogue, Shopping Cart and Checkout,
    Payment Processing and Invoicing, Order Management and Fulfilment,
    Returns and Dispute Resolution, Review and Rating System,
    Promotions and Discount Management, Notifications and Alerts,
    Admin Moderation and Fraud Detection, Analytics and Reporting Dashboard,
    External Integration and API Access, User Account and Role Management

  IOT_CONTROL:
    Device Registration and Pairing, Device Status Monitoring,
    Remote Control and Command Execution, Automation Rules and Scheduling,
    Scene and Group Control, Energy Consumption Monitoring,
    Alerts and Anomaly Detection, Firmware and Software Update Management,
    User Account and Role Management, Guest and Shared Access Management,
    Reporting and History, Help and Support Centre

  CONTENT_PLATFORM:
    Content Creation and Upload, Content Categorisation and Tagging,
    Content Search and Discovery, Content Playback or Viewing,
    Subscription and Access Control, Comments and Community Interaction,
    Creator Analytics and Revenue, Content Moderation,
    Notifications and Recommendations, User Account and Role Management

  ENTERPRISE_MGMT:
    Employee or User Onboarding, Role and Permission Management,
    Core Business Process Workflows, Task and Assignment Management,
    Document and File Management, Reporting and Analytics,
    Integration with External Business Systems, Audit Trail and Compliance Logging,
    Notifications and Alerts, User Account and Role Management

  HEALTH_WELLNESS:
    User Health Profile, Goal Setting and Progress Tracking,
    Activity or Symptom Logging, Wearable and Device Integration,
    Health Insights and Recommendations, Appointment or Session Scheduling,
    Notifications and Reminders, Data Export and Sharing,
    Compliance and Data Privacy Tools, User Account and Role Management

  ECOMMERCE:
    Product Catalogue and Search, Product Detail and Reviews,
    Shopping Cart and Wishlist, Checkout and Payment Processing,
    Order Tracking and History, Returns and Refund Management,
    Promotions and Loyalty Programme, Seller or Inventory Management,
    Notifications and Alerts, User Account and Role Management

  FINANCIAL:
    Account Registration and Verification (KYC), Balance and Transaction View,
    Payment and Transfer Initiation, Recurring Payments and Scheduling,
    Invoicing and Billing, Financial Reporting and Statements,
    Fraud Detection and Alerts, Compliance and Regulatory Reporting,
    User Account and Role Management

  SOCIAL_NETWORK:
    User Profile and Identity, Following and Connection Management,
    Content Feed and Discovery, Post Creation and Media Upload,
    Reactions, Comments and Sharing, Direct Messaging,
    Notifications and Activity Alerts, Groups and Communities,
    Content Moderation and Reporting, User Account and Role Management

  EDTECH:
    Course Catalogue and Enrolment, Lesson and Content Delivery,
    Assessment and Quizzing, Progress Tracking and Certificates,
    Discussion Forum and Peer Interaction, Instructor Tools and Analytics,
    Subscription and Payment, Notifications and Reminders,
    User Account and Role Management

RULE C — FOR EVERY PHYSICAL DEVICE OR SENSOR mentioned, create a domain for \
  its CONTROL FUNCTION (not just connectivity):
  thermostat → "Temperature Control", cameras → "Security Camera Monitoring".

RULE D — DECOMPOSE compound features into separate domains. For example, if the customer \
  mentions "users can search and book appointments", that is TWO domains: \
  "Appointment Search" AND "Booking Management". \
  And if they mention "employers can post and manage jobs", that is also TWO: \
  "Job Posting and Publishing" AND "Employer Dashboard and Management".

RULE E — DO NOT merge distinct user-role workflows into one domain. \
  For example, "Profile Management" for a job seeker and "Employer Profile Management" \
  are separate domains when the system has distinct user classes.

RULE F — Domain names must be 2-6 words, title-case, USER-FACING function names. \
  Do NOT include NFRs, implementation details, or technology names.

STEP 3 — OUTPUT.
Return ONLY a JSON array of domain name strings, covering every domain from \
Step 2. Output the COMPLETE array even if it has 20+ items. Stopping early is a critical failure.

Your JSON array:"""

# ---------------------------------------------------------------------------
# RESEED PROMPT
# ---------------------------------------------------------------------------
_RESEED_PROMPT = """\
You are an expert Requirements Engineer. Your colleague is conducting a \
requirements elicitation interview with a customer for the project "{project_name}". \
You previously identified functional domains from the customer's first message. \
Now that the interview has progressed, you have richer context and must \
identify ALL REMAINING functional domains not yet covered.

CUSTOMER'S FIRST MESSAGE:
---
{description}
---

REQUIREMENTS EXTRACTED SO FAR ({req_count} total):
{req_sample}

DOMAINS ALREADY IDENTIFIED (do NOT repeat these):
{current_domains}

YOUR TASK — identify missing domains using THREE lenses:

LENS 1 — REQUIREMENTS SIGNAL: Review the requirements extracted so far. \
  Do any of them imply a functional domain that is not in the list above? \
  For example, a requirement about "subscription tiers" implies a \
  "Subscription and Billing Management" domain; a requirement about \
  "employer verification" implies an "Employer Verification and Trust" domain.

LENS 2 — SYSTEM-TYPE COMPLETENESS: Based on the system type ({project_name}), \
  which domains from the canonical taxonomy for this system type are still missing? \
  Common gaps for complex systems include:
  - Admin and moderation workflows (often forgotten until late)
  - Compliance, audit, and data privacy tools (GDPR, right to erasure, consent)
  - Subscription, billing, and payment management
  - External partner or API integration management
  - Fraud detection or trust and safety features
  - Analytics dashboards for each distinct user class
  - Onboarding and guided setup flows
  - Help, support, and feedback collection

LENS 3 — ELICITATION GAPS: Are there user classes mentioned in the requirements \
  who do not yet have their own dedicated workflow domains? Each major user class \
  (job seeker, employer, admin, recruiter, partner) should have at least one \
  domain representing their primary workflow.

Return ONLY a JSON array of NEW domain name strings not already in the list above. \
Each name: 2-6 words, title-case, user-facing function.
If no domains are missing, return an empty array: []"""

# ---------------------------------------------------------------------------
# NFR CLASSIFY PROMPT
# ---------------------------------------------------------------------------
_NFR_CLASSIFY_PROMPT = """\
Classify this requirement into one IEEE-830 NFR category:
  performance, usability, security_privacy, reliability, compatibility, maintainability

Requirement: "{text}"
Reply with ONLY the category key."""

# ---------------------------------------------------------------------------
# SUBDIM CLASSIFY PROMPT
# ---------------------------------------------------------------------------
_SUBDIM_CLASSIFY_PROMPT = """\
Classify into one: data, actions, constraints, automation, edge_cases
Requirement: "{text}"
Reply with ONLY one word."""

# ---------------------------------------------------------------------------
# DOMAIN MATCH PROMPT
# ---------------------------------------------------------------------------
_DOMAIN_MATCH_PROMPT = """\
Which domain does this requirement belong to?

Requirement: "{req_text}"

Domains:
{domain_list}

Reply with ONLY the domain key (text before the colon). If none fit, reply "none"."""

# ---------------------------------------------------------------------------
# DECOMPOSE REQUIREMENTS INTO ATOMIC REQUIREMENTS PROMPT
# ---------------------------------------------------------------------------
_DECOMPOSE_PROMPT = """You are a requirements engineering expert helping a colleague write a complete
IEEE 830-1998 SRS for the "{project_name}" system.

Your task: generate MISSING atomic requirements for the "{domain_label}" domain.

REQUIREMENTS ALREADY WRITTEN FOR THIS DOMAIN:
{existing_reqs}

ALL OTHER REQUIREMENTS ALREADY IN THE SRS (do NOT repeat any of these):
{all_other_reqs}

{coverage_guidance}

GENERATION RULES:
- Write ONLY requirements that are COMPLETELY ABSENT from both lists above.
- Each requirement: ONE atomic "The system shall [verb] [object] [measurable constraint]."
- Every requirement MUST include a specific, measurable criterion (number, threshold,
  time limit, data format, percentage, or verifiable condition).
  BAD:  "The system shall handle errors gracefully."
  GOOD: "The system shall display an error message within 500ms if a matching request
         fails, including the failure reason and a suggested corrective action."
- If a requirement is clearly a quality attribute (performance, security, reliability,
  usability, compliance), prefix it with [NFR] so the caller can store it correctly.
  Example: "[NFR] The system shall encrypt all candidate profile data at rest using
  AES-256 and in transit using TLS 1.3 or higher."
- Do NOT generate duplicate or near-duplicate requirements.
- Return ONLY a JSON array of strings. No explanation, no preamble."""

# ---------------------------------------------------------------------------
# PROJECT NAME PROMPT
# ---------------------------------------------------------------------------
_PROJECT_NAME_PROMPT = """\
A stakeholder described their system: "{message}"
What is the system name (2-5 words)? Reply with ONLY the name."""

# ---------------------------------------------------------------------------
# SYSTEM COMPLEXITY CLASSIFICATION
# ---------------------------------------------------------------------------

_COMPLEXITY_PROMPT = """You are an expert Requirements Engineer classifying the complexity of a software system
for the purpose of calibrating how deeply to elicit requirements.

Use the three-level taxonomy from IEEE 830 and standard RE practice:

SIMPLE — A system serving a single user class with a narrowly bounded functional scope,
  few or no external integrations, no AI/ML components, and low data volume.
  Examples: personal habit tracker, single-user note-taking app, basic to-do list.

MEDIUM — A system serving 2-4 distinct user classes OR requiring integration with
  external APIs/services OR managing a moderately complex data model, but with
  well-understood, bounded business rules and no adaptive/intelligent components.
  Examples: multi-user project management tool, e-commerce storefront, booking system.

COMPLEX — A system with 5+ stakeholder classes OR AI/ML/algorithmic decision-making OR
  cross-domain integrations (IoT, government APIs, payment networks, real-time data feeds)
  OR regulatory compliance requirements (GDPR, HIPAA, PCI-DSS) OR distributed architecture.
  Examples: AI-based job matching platform, smart home automation system, healthcare platform.

IMPORTANT: Classify based on the DEPLOYMENT CONTEXT described, not just the surface feature set.
A habit tracker for a single user is SIMPLE; the same habit tracker deployed by an enterprise
with analytics, multi-tenancy, and API integrations is MEDIUM or COMPLEX.

PROJECT: "{project_name}"
DESCRIPTION: "{description}"
DOMAIN COUNT: {domain_count}
STAKEHOLDER INDICATORS: {stakeholder_hints}
INTEGRATION INDICATORS: {integration_hints}

Reply with ONLY one word: simple, medium, or complex."""

# ---------------------------------------------------------------------------
# DOMAIN REQUIREMENT COVERAGE TEMPLATE
# ---------------------------------------------------------------------------

_DOMAIN_TEMPLATE_PROMPT = """You are an expert Requirements Engineer helping a colleague elicit requirements
for a formal IEEE 830-1998 SRS document.

Your colleague has just received this reply from the customer:

CUSTOMER MESSAGE:
---
{user_message}
---

This reply was in response to a question about the "{domain_label}" feature
of the "{project_name}" system (complexity level: {complexity}).

REQUIREMENTS ALREADY WRITTEN FOR THIS FEATURE:
{existing_reqs}

YOUR TASK:
Generate a structured coverage checklist — a list of requirement DIMENSIONS
that a feature "{domain_label}" must address. This checklist will be
injected into your colleague's system prompt so they know exactly what to
elicit next for this feature.

Ground your checklist in standard RE coverage dimensions for this feature type.
For each dimension, write one line: a short label followed by a colon and a
brief description of what must be specified.

Generate ONLY dimensions that are directly part of "{domain_label}".
Do NOT include dimensions that belong to other features (e.g. if the feature is
"Registration", do not include "System Matching" or "Notification" dimensions).

Cover ALL of the following RE coverage categories as relevant to this feature:

1. DATA — what information the system must store, validate, and manage
2. ACTOR ACTIONS — what each user role can do, with their preconditions
3. SYSTEM AUTOMATION — what the system does automatically without user input
4. BUSINESS RULES — validation logic, constraints, policies, calculations
5. ERROR & EDGE CASES — what happens when inputs are missing, invalid, or extreme
6. INTEGRATION POINTS — external systems, APIs, or devices this domain touches
7. DOMAIN-SPECIFIC NFRs — performance, security, or compliance rules specific to this domain
   (do NOT list generic system-wide NFRs already covered elsewhere)

Rules:
For simple or supporting domains, 4-6 dimensions are sufficient. Only expand to 10+ for core workflow domains.
Format your response as a plain numbered list. Each item: one line, concise.
Ground your dimensions in this specific system. Do not copy examples from unrelated domains
Do NOT use markdown headers.
Return ONLY the checklist, no preamble or explanation."""

# Minimum fraction of in-scope (non-excluded) domains that must be confirmed
# before the domain gate is considered satisfied. Mirrors the constant in
# prompt_architect.py — both must agree.
_DOMAIN_GATE_COVERAGE_FRACTION = 0.80

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------
class GapSeverity(str, Enum):
    CRITICAL  = "critical"
    IMPORTANT = "important"
    OPTIONAL  = "optional"


# ---------------------------------------------------------------------------
# IEEE-830 coverage checklist (Volere removed — IT8)
# ---------------------------------------------------------------------------
COVERAGE_CHECKLIST: dict[str, dict] = {
    "purpose": {
        "label":       "System Purpose & Goals",
        "severity":    GapSeverity.CRITICAL,
        "description": "What problem does the system solve and why does it exist?",
        "ieee830_ref": "1.1",
    },
    "scope": {
        "label":       "System Scope & Boundaries",
        "severity":    GapSeverity.CRITICAL,
        "description": "What is inside and outside the system boundary?",
        "ieee830_ref": "1.2",
    },
    "product_prespective": {
        "label":       "Product Perspective & Context",
        "severity":    GapSeverity.IMPORTANT,
        "description": "How does the system fit into a larger context or interact with other systems?",
        "ieee830_ref": "2.1",
    },
    "user_classes": {
        "label":       "User Classes & Characteristics",
        "severity":    GapSeverity.CRITICAL,
        "description": "Who are the users and stakeholders of the system?",
        "ieee830_ref": "2.3",
    },
    "general_constraints": {
        "label":       "General Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What general constraints, assumptions, or dependencies exist?",
        "ieee830_ref": "2.4",
    },
    "assumptions_dependencies": {
        "label":       "Assumptions & Dependencies",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What assumptions are we making and what dependencies exist?",
        "ieee830_ref": "2.5",
    },
    "user_interfaces": {
        "label":       "User Interface",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What are the requirements for the user interface and user experience?",
        "ieee830_ref": "3.1.1",
    },
    "software_interfaces": {
        "label":       "Software Interface",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What are the requirements for software interfaces and interactions?",
        "ieee830_ref": "3.1.3",
    },
    "communication_interfaces": {
        "label":       "Communication Interface",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What are the requirements for communication interfaces and interactions?",
        "ieee830_ref": "3.1.4",
    },
    "functional": {
        "label":       "Functional Requirements",
        "severity":    GapSeverity.CRITICAL,
        "description": "What must the system do? Core features and behaviours.",
        "ieee830_ref": "3.2",
        "_use_req_store": True,
    },
    "performance": {
        "label":       "Performance Requirements",
        "severity":    GapSeverity.CRITICAL,
        "description": "How fast must the system respond? What load must it handle?",
        "ieee830_ref": "3.3",
    },
    "constraints": {
        "label":       "Design & Implementation Constraints",
        "severity":    GapSeverity.IMPORTANT,
        "description": "What constraints exist on the design or implementation?",
        "ieee830_ref": "3.5",
    },
    "reliability": {
        "label":       "Reliability",
        "severity":    GapSeverity.CRITICAL,
        "description": "How reliable must the system be? What happens when it fails?",
        "ieee830_ref": "3.6.1",
    },
    "availability": {
        "label":       "Availability",
        "severity":    GapSeverity.CRITICAL,
        "description": "How available must the system be? Any uptime requirements?",
        "ieee830_ref": "3.6.2",
    },
    "security_privacy": {
        "label":       "Security & Privacy Requirements",
        "severity":    GapSeverity.CRITICAL,
        "description": "How must the system protect data and prevent unauthorised access?",
        "ieee830_ref": "3.6.3",
    },
    "maintainability": {
        "label":       "Maintainability & Extensibility",
        "severity":    GapSeverity.CRITICAL,
        "description": "How will the system be maintained, updated, and extended over time?",
        "ieee830_ref": "3.6.4",
    },
    "compatibility": {
        "label":       "Compatibility & Portability",
        "severity":    GapSeverity.CRITICAL,
        "description": "What platforms must the system run on? What must it integrate with?",
        "ieee830_ref": "3.6.5",
    },
    "usability": {
        "label":       "Usability & Accessibility",
        "severity":    GapSeverity.CRITICAL,
        "description": "How easy must the system be to use? Any accessibility requirements?",
        "ieee830_ref": "3.6.6",
    }
}
