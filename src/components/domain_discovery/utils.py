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
SEED_PROMPT = """\
You are an expert Requirements Engineer. A structured project brief has been \
collected from the customer. Your task is to identify every functional domain \
that a complete requirements elicitation interview must cover for this system.
 
PROJECT: "{project_name}"
 
PROJECT BRIEF (confirmed with the customer):
{project_brief}
{extra_context}
 
═══════════════════════════════════════════════════════
STEP 1 — ASSESS AMBITION LEVEL
═══════════════════════════════════════════════════════
Read the brief and determine how large this system is:
 
  FOCUSED      — 1-3 features, single user class, no integrations, simple scope.
                 → Target 4-7 domains total.
  STANDARD     — Multiple user classes OR 3-6 distinct features OR one integration.
                 → Target 8-12 domains total.
  COMPREHENSIVE — 3+ user classes OR AI/ML OR multiple integrations OR
                  compliance requirements (GDPR, HIPAA, PCI-DSS) OR
                  the customer explicitly described a complex platform.
                 → Target 15+ domains total.
 
═══════════════════════════════════════════════════════
STEP 2 — CLASSIFY THE SYSTEM TYPE
═══════════════════════════════════════════════════════
Identify the primary archetype (one only) from the brief above:
 
  MATCHING_PLATFORM | MARKETPLACE | IOT_CONTROL | CONTENT_PLATFORM |
  ENTERPRISE_MGMT | HEALTH_WELLNESS | ECOMMERCE | FINANCIAL |
  SOCIAL_NETWORK | EDTECH | GENERAL
 
═══════════════════════════════════════════════════════
STEP 3 — BUILD THE DOMAIN LIST (two-tier model)
═══════════════════════════════════════════════════════
 
TIER 1 — STATED DOMAINS (always include, derive from the brief):
  For every feature listed in "Core features", create one domain.
  For every user class in "User classes", ensure their primary workflow has a domain.
  RULE D — decompose compound features into separate domains:
    "Users can search and book appointments" → "Appointment Search" + "Booking Management"
    Apply RULE D only to what the brief states — do not decompose inferred features.
 
TIER 2 — STRONGLY IMPLIED DOMAINS (include only if the brief signals a need):
  Add a domain from the taxonomy below ONLY when ALL of the following are true:
    1. The domain is absent from Tier 1.
    2. The brief contains a direct signal (a feature, user class, or integration)
       that this domain would serve.
    3. The system cannot function for the customer's stated goals without it.
  Do NOT add a domain simply because it is common for this system type.
  "Out of scope" fields in the brief are hard exclusions — never add those.
 
SYSTEM-TYPE TAXONOMY (reference for Tier 2 — do not dump the full list):
 
  MATCHING_PLATFORM:
    Registration and Profile Management, Profile Search and Discovery,
    AI Matching and Recommendations, Application or Expression of Interest,
    Communication and Messaging, Review and Rating System,
    Saved Items and Shortlists, Notifications and Alerts, Subscription and Billing,
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
 
  GENERAL:
    User Account and Role Management, Core Feature Workflow,
    Search and Discovery, Notifications and Alerts,
    Reporting and History, Help and Support Centre
 
CROSS-CUTTING INCLUSIONS — add these only when the brief gives explicit evidence:
  "User Account and Role Management" — only if 2+ user classes OR login/auth mentioned.
  "Notifications and Alerts"         — only if alerts, reminders, or events mentioned.
  "Admin" domains                    — only if admin role, moderation, or oversight mentioned.
  "Analytics and Reporting"          — only if dashboards, reports, or data insights mentioned.
  "Compliance and Data Privacy"      — only if GDPR/HIPAA/PCI-DSS or personal data mentioned.
  "External Integration"             — only if integration points field is non-empty.
 
ROLE SEPARATION — create separate domains per user class ONLY for explicitly named
  distinct classes in the brief. Do not invent user classes not listed.
 
═══════════════════════════════════════════════════════
STEP 4 — CONSTRAINTS CHECK
═══════════════════════════════════════════════════════
Review the "Known constraints" and "Integration points" brief fields.
For each constraint or integration mentioned, verify that a domain exists to
cover it. If not, add the minimum domain required to address it.
 
Example: "Integration points: Google Calendar API" → requires an
"External Calendar Integration" domain if not already covered.
 
═══════════════════════════════════════════════════════
STEP 5 — SELF-CHECK
═══════════════════════════════════════════════════════
Before outputting, verify:
  1. Every domain traces back to a field in the project brief.
  2. No domain covers anything listed in "Out of scope".
  3. Total count matches the ambition level from Step 1.
  4. No two domains on the list represent the same workflow under different names.
  5. No user class in the brief is left without at least one domain for their
     primary workflow.
 
Revise if any check fails.
 
═══════════════════════════════════════════════════════
STEP 6 — OUTPUT
═══════════════════════════════════════════════════════
Return ONLY a JSON array of domain name strings.
Each name: 2-6 words, title-case, user-facing function name.
No NFRs, no implementation details, no technology names.
Output the COMPLETE array. Stopping early is a critical failure.
 
Your JSON array:"""
# ---------------------------------------------------------------------------
# RESEED PROMPT
# ---------------------------------------------------------------------------
RESEED_PROMPT = """\
You are an expert Requirements Engineer. A requirements elicitation interview \
is in progress for the project "{project_name}", complexity: {complexity}).

Your task is to identify functional domains that are GENUINELY MISSING from \
the current domain list — domains that have clear evidence in the interview \
so far but are not yet being tracked.

PROJECT BRIEF (confirmed with the customer):
{project_brief}
{description}

REQUIREMENTS EXTRACTED SO FAR ({req_count} total):
{req_sample}

DOMAINS ALREADY IN THE GATE — do NOT suggest any of these, whether confirmed,
partial, or unprobed:
{current_domains}

─────────────────────────────────────────────────────────
STEP 1 — REQUIREMENTS SIGNAL (primary lens, highest weight)
─────────────────────────────────────────────────────────
Read every requirement in the sample above. For each one, ask:
"Does this requirement imply a distinct functional workflow that is NOT
already represented by any domain in the gate above?"

A domain is implied if:
  - Multiple requirements reference an entity or workflow with no owning domain, OR
  - A requirement references an actor (user class) who has no dedicated domain, OR
  - A requirement describes system behaviour that clearly belongs to a
    separate user-facing feature, not a sub-concern of an existing domain.

A domain is NOT implied if:
  - It is a sub-dimension (data, actions, constraints) of a domain already in the gate.
  - It is an NFR or quality concern, not a functional workflow.
  - It describes the same workflow as an existing domain under a different name.

─────────────────────────────────────────────────────────
STEP 2 — STATED USER CLASS GAPS (secondary lens)
─────────────────────────────────────────────────────────
Look at the requirements and description. Identify every distinct user class
that is explicitly mentioned (do NOT invent user classes not in the text).

For each user class found: does that user class have at least one domain in
the gate that covers their primary workflow? If not, that is a gap.

─────────────────────────────────────────────────────────
STEP 3 — SYSTEM-TYPE COMPLETENESS CHECK (tertiary lens, apply with restraint)
─────────────────────────────────────────────────────────
System type: {system_type} | Complexity: {complexity}

Only apply this lens if complexity is "medium" or "complex".
For simple systems, skip this lens entirely.

Review the standard domains for system type "{system_type}" below.
Suggest a domain from this list ONLY if ALL three conditions hold:
  1. The domain is absent from the current gate.
  2. The requirements or description contain at least one signal (a feature,
     user action, or entity) that this domain would serve.
  3. The system cannot function correctly for the customer's stated goals
     without this domain being addressed.

Do NOT suggest a domain purely because it is common for this system type.
Silence is not evidence of need.

Standard domains by system type (reference only — do not dump the full list):

  MATCHING_PLATFORM: Registration and Profile Management, Profile Search and Discovery,
    AI Matching and Recommendations, Application or Expression of Interest,
    Communication and Messaging, Review and Rating System, Subscription and Billing,
    Admin Moderation and Content Review, Analytics and Reporting Dashboard,
    Compliance and Data Privacy Tools, Notifications and Alerts,
    User Account and Role Management, Help and Support Centre

  MARKETPLACE: Seller Registration and Listing Management, Buyer Registration and Search,
    Product or Service Catalogue, Shopping Cart and Checkout,
    Payment Processing and Invoicing, Order Management and Fulfilment,
    Returns and Dispute Resolution, Review and Rating System,
    Admin Moderation and Fraud Detection, Analytics and Reporting Dashboard,
    Notifications and Alerts, User Account and Role Management

  IOT_CONTROL: Device Registration and Pairing, Device Status Monitoring,
    Remote Control and Command Execution, Automation Rules and Scheduling,
    Energy Consumption Monitoring, Alerts and Anomaly Detection,
    Firmware and Software Update Management, Guest and Shared Access Management,
    User Account and Role Management, Reporting and History

  CONTENT_PLATFORM: Content Creation and Upload, Content Categorisation and Tagging,
    Content Search and Discovery, Subscription and Access Control,
    Creator Analytics and Revenue, Content Moderation,
    Notifications and Recommendations, User Account and Role Management

  ENTERPRISE_MGMT: Employee or User Onboarding, Role and Permission Management,
    Core Business Process Workflows, Task and Assignment Management,
    Document and File Management, Reporting and Analytics,
    Audit Trail and Compliance Logging, Integration with External Business Systems,
    Notifications and Alerts, User Account and Role Management

  HEALTH_WELLNESS: User Health Profile, Goal Setting and Progress Tracking,
    Activity or Symptom Logging, Wearable and Device Integration,
    Appointment or Session Scheduling, Compliance and Data Privacy Tools,
    Notifications and Reminders, User Account and Role Management

  ECOMMERCE: Product Catalogue and Search, Shopping Cart and Wishlist,
    Checkout and Payment Processing, Order Tracking and History,
    Returns and Refund Management, Promotions and Loyalty Programme,
    Seller or Inventory Management, Notifications and Alerts,
    User Account and Role Management

  FINANCIAL: Account Registration and Verification (KYC), Balance and Transaction View,
    Payment and Transfer Initiation, Invoicing and Billing,
    Fraud Detection and Alerts, Compliance and Regulatory Reporting,
    User Account and Role Management

  SOCIAL_NETWORK: User Profile and Identity, Content Feed and Discovery,
    Post Creation and Media Upload, Direct Messaging,
    Notifications and Activity Alerts, Groups and Communities,
    Content Moderation and Reporting, User Account and Role Management

  EDTECH: Course Catalogue and Enrolment, Lesson and Content Delivery,
    Assessment and Quizzing, Progress Tracking and Certificates,
    Instructor Tools and Analytics, Subscription and Payment,
    Notifications and Reminders, User Account and Role Management

  GENERAL: Core Feature Workflow, User Account and Role Management,
    Notifications and Alerts, Reporting and History, Help and Support Centre

─────────────────────────────────────────────────────────
STEP 4 — NECESSITY TEST (apply to every candidate domain)
─────────────────────────────────────────────────────────
Before adding any domain to your output, apply this test:

  "If this domain is never elicited, will the customer's system — as they
   described it — be functionally incomplete or broken?"

If YES → include it.
If NO, or UNCERTAIN → exclude it. When in doubt, leave it out.

─────────────────────────────────────────────────────────
STEP 5 — OUTPUT
─────────────────────────────────────────────────────────
Return ONLY a JSON array of NEW domain name strings.
- Do NOT repeat any domain already in the gate (confirmed, partial, or unprobed).
- Each name: 2-6 words, title-case, user-facing function.
- If no domains pass the necessity test, return: []
- For simple systems with all core domains already present: almost always return []

Your JSON array:"""

# ---------------------------------------------------------------------------
# NFR CLASSIFY PROMPT
# ---------------------------------------------------------------------------
NFR_CLASSIFY_PROMPT = """\
Classify this requirement into one IEEE-830 NFR category:
  performance, usability, security_privacy, reliability, compatibility, maintainability

Requirement: "{text}"
Reply with ONLY the category key."""

# ---------------------------------------------------------------------------
# SUBDIM CLASSIFY PROMPT
# ---------------------------------------------------------------------------
SUBDIM_CLASSIFY_PROMPT = """\
Classify into one: data, actions, constraints, automation, edge_cases
Requirement: "{text}"
Reply with ONLY one word."""

# ---------------------------------------------------------------------------
# DOMAIN MATCH PROMPT
# ---------------------------------------------------------------------------
DOMAIN_MATCH_PROMPT = """\
Which domain does this requirement belong to?

Requirement: "{req_text}"

Domains:
{domain_list}

Reply with ONLY the domain key (text before the colon). If none fit, reply "none"."""

# ---------------------------------------------------------------------------
# DECOMPOSE REQUIREMENTS INTO ATOMIC REQUIREMENTS PROMPT
# ---------------------------------------------------------------------------
DECOMPOSE_PROMPT = """You are a requirements engineering expert helping a colleague write a complete
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
PROJECT_NAME_PROMPT = """\
PROJECT BRIEF (confirmed with the customer):
{project_brief}

What is the system name (2-5 words)? Reply with ONLY the name."""

# ---------------------------------------------------------------------------
# SYSTEM COMPLEXITY CLASSIFICATION
# ---------------------------------------------------------------------------

COMPLEXITY_PROMPT = """You are an expert Requirements Engineer classifying the complexity of a software system
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
PROJECT BRIEF (confirmed with the customer):
{project_brief}

DOMAIN COUNT: {domain_count}
STAKEHOLDER INDICATORS: {stakeholder_hints}
INTEGRATION INDICATORS: {integration_hints}

Reply with ONLY one word: simple, medium, or complex."""

# ---------------------------------------------------------------------------
# DOMAIN REQUIREMENT COVERAGE TEMPLATE
# ---------------------------------------------------------------------------

DOMAIN_TEMPLATE_PROMPT = """You are an expert Requirements Engineer helping a colleague elicit requirements
for a formal IEEE 830-1998 SRS document.
PROJECT: "{project_name}"
Assumed System Complexity Level: "{complexity}"
PROJECT BRIEF (confirmed with the customer):
{project_brief}

REQUIREMENTS ALREADY WRITTEN FOR THIS FEATURE "{domain_label}":
{existing_reqs}

YOUR TASK:
Generate a coverage checklist for the "{domain_label}" feature.
Each item is one concrete dimension that must be elicited before this feature
is complete. This list is injected into your colleague's system prompt as a
per-turn guide.

COVERAGE DIMENSIONS — evaluate each of the following 7 categories and include
an item ONLY if it genuinely applies to this specific domain. Do not force a
category that has no meaningful content for this domain type.

  actions           — what human actors explicitly initiate in this domain
                      SKIP this category if the domain has no direct user interaction
                      (e.g. background sync, scheduled jobs, pure integration layers)

  data              — what information the system must store, validate, and manage
                      (field names, formats, constraints, retention rules)

  access_control    — which user roles can perform which actions or see which data;
                      visibility rules and permission boundaries for this domain
                      SKIP only if the domain is single-role with no permission variation

  constraints       — business rules, validation policies, hard limits, and
                      regulatory obligations that govern this domain's behaviour

  automation        — what the system does in this domain automatically, without
                      user input (triggered by events, schedules, or thresholds)
                      SKIP if the domain is purely read-only or has no system-initiated behaviour

  state_transitions — the lifecycle stages an entity in this domain passes through
                      and the rules/triggers for moving between them
                      (e.g. ticket: open → in-progress → resolved → closed)
                      SKIP if the domain manages no stateful entities

  edge_cases        — what happens when inputs are missing, invalid, extreme,
                      concurrent, or when dependent systems are unavailable

Additionally, add up to 2 items under this optional category if applicable:
  nfr               — domain-specific performance, security, or compliance obligations
                      NOT already captured as a system-wide requirement

SCOPE RULES:
- Include a category ONLY if it has real content for "{domain_label}".
- Do NOT include dimensions that belong to other features.
- For simple or supporting domains (e.g. Help Centre, Notifications): 4-6 items total.
- For core workflow domains (e.g. Payment, Booking, Matching, Registration): 8-12 items.
- Ground every item in this specific system — no generic filler lines.

FORMAT: plain numbered list.
Each item must follow this pattern: "dimension_label: one concrete sentence describing
what must be specified for {domain_label} in {project_name}."

Example items:
  "state_transitions: A support ticket moves through: open → assigned → in-progress → resolved → closed; define the trigger and allowed actors for each transition."
  "data: Store ticket ID, reporter user ID, description, priority level, assigned agent, status, and timestamps for creation and last update."
  "automation: Automatically escalate a ticket to senior support if it remains unresolved for more than 48 hours."
  "access_control: Only agents assigned to a ticket may update its status; admins may reassign or close any ticket regardless of assignment."
  "edge_cases: Define behaviour when a ticket is submitted by a user whose account is suspended, or when the assigned agent's account is deactivated mid-ticket."

Return ONLY the numbered checklist. No preamble, no markdown headers, no explanation."""

# Minimum fraction of in-scope (non-excluded) domains that must be confirmed
# before the domain gate is considered satisfied. Mirrors the constant in
# prompt_architect.py — both must agree.
DOMAIN_GATE_COVERAGE_FRACTION = 0.80

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
