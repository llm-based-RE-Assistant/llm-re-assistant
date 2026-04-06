# Domain Coverage Gate — Quick Reference

## 🎯 What It Does

The Domain Coverage Gate ensures **all relevant system domains** are systematically explored before generating the SRS.

## 🔄 Lifecycle

```
Session Start
    ↓
Turn 1 (First User Message)
    ↓ LLM generates project-specific domains
Domain Gate Created (5-8 domains)
    ↓
Turns 2-5 (Elicitation)
    ↓ LLM probes each domain
    ↓
After Turn 5 (Gate Expansion Check)
    ↓ LLM evaluates if new domains needed
Domain Gate May Expand (± new domains)
    ↓
Turns 6+ (Continue Elicitation)
    ↓
Gate Fully Satisfied
    ↓ SRS Generation Permitted
```

## 📊 Status Indicators

| Icon | Status        | Meaning                                |
| ---- | ------------- | -------------------------------------- |
| ✅   | **Confirmed** | Domain thoroughly explored             |
| 🔶   | **Partial**   | Domain mentioned but not fully covered |
| ⬜   | **Unprobed**  | Domain not yet discussed               |
| ❌   | **Excluded**  | Stakeholder explicitly excluded        |

## 🚀 Trigger Points

### **Turn 1: Domain Generation**

```python
# After first user message
generate_domain_gate_from_llm(user_message)
# Creates project-specific domain list
```

### **Turn 5: Domain Expansion**

```python
# After 5 turns of conversation
expand_domain_gate_from_llm(
    current_gate=current_domains,
    conversation_corpus=all_5_turns,
    requirements_texts=extracted_reqs
)
# Adds new domains if needed
```

## 📝 Domain Structure

```python
{
    "domain_key": {
        "label": "Human Name",              # Displayed to user
        "detection_kw": ["keyword1", ...],  # Triggers confirmation
        "exclusion_kw": ["no keyword", ...],# Triggers exclusion
        "fallback_probe": "Question?"       # Asked if not discussed
    }
}
```

## 🔧 Key Functions

### **For Implementation:**

- `generate_domain_gate_from_llm()` — Initial generation
- `expand_domain_gate_from_llm()` — Expansion evaluation

### **For Analysis:**

- `compute_domain_gate(state, domain_gate)` — Calculate domain status
- `gate_is_satisfied(gate_status)` — Check if all domains confirmed/excluded

### **For SRS:**

- `is_srs_generation_permitted(state)` — Hard gate check

## 💾 Storage

```python
# Instance variable in PromptArchitect
class PromptArchitect:
    domain_gate: dict[str, dict] = field(
        default_factory=lambda: dict(DEFAULT_DOMAIN_COVERAGE_GATE)
    )
```

## 🎓 Example: Smart Home System

**Turn 1 User Message:**

> "I need a smart home system that controls temperature, lighting,
> and allows remote access via a mobile app."

**Generated Domains:**

1. ✅ Climate Control (temperature mentioned)
2. ✅ Appliance & Lighting (lighting mentioned)
3. ✅ Remote Access (mobile app mentioned)
4. 🔶 Security & Alarm (partially implied)
5. ⬜ Scheduling & Plans
6. ⬜ User Accounts & Roles
7. ⬜ Historical Data & Logs
8. ⬜ Hardware Connectivity

**After Turn 5:**

- Expanding based on "energy monitoring" mentions
- Adding: "Energy Analytics" domain

## ⚡ Critical Rules

- 🚫 **Cannot** skip domains because stakeholder didn't mention them
- 🚫 **Cannot** generate SRS while any domain is UNPROBED
- ✅ **Must** ask fallback probe questions for skipped domains
- ✅ **Must** expand domains if new requirements emerge

## 🔍 Fallback Mechanism

```
LLM Call Fails
    ↓
System logs warning
    ↓
Reverts to DEFAULT_DOMAIN_COVERAGE_GATE
    ↓
Conversation continues normally
```

## 📊 Monitoring

**In Assistant Context (every turn):**

```
━━━ DOMAIN COVERAGE GATE  [5/8 — 62%] ━━━
  ✅ Market Analysis
  ✅ Product Features
  ✅ Revenue Streams
  🔶 Pricing Strategy
      ↳ Probe: "What pricing model do you propose?"
  ⬜ Competitive Analysis
      ↳ Probe: "Who are your main competitors?"
  ⬜ Risk Management
  ⬜ Success Metrics
```

## 📋 Default Domains (Smart Home Example)

1. **Climate Control** — Temperature & humidity management
2. **Security & Alarm** — Doors, windows, locks, sensors
3. **Appliance & Lighting** — Remote on/off, dimming
4. **Scheduling & Plans** — Automation, routines, presets
5. **Remote Access** — App/web control
6. **User Accounts & Roles** — Permissions & access control
7. **Historical Data & Logs** — Storage, analytics, reporting
8. **Hardware Connectivity** — Sensors, hubs, network protocols

## 🎯 Design Philosophy

**"No Domain Left Behind"**

Every relevant system domain must be explicitly confirmed or excluded before SRS generation. This prevents "we forgot to ask about X" errors.
