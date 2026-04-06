# Domain Coverage Gate — Dynamic Implementation (Iteration 4)

## Overview

The **Domain Coverage Gate** is a critical elicitation mechanism that ensures structured exploration of all relevant system domains before generating the SRS. Previously, the `DOMAIN_COVERAGE_GATE` was referenced but never defined. This document explains the complete implementation.

---

## Problem Solved

- ❌ **Before**: `DOMAIN_COVERAGE_GATE` was undefined, causing runtime errors
- ✅ **After**: Dynamic LLM-based generation and expansion throughout the conversation

---

## Architecture

### 1. **Default Domain Gate (Smart Home Example)**

File: `src/components/prompt_architect.py` → `DEFAULT_DOMAIN_COVERAGE_GATE`

```python
{
    "climate_control": {
        "label": "Climate Control",
        "detection_kw": ["temperature", "humidity", "climate", ...],
        "exclusion_kw": ["no climate", "not climate", ...],
        "fallback_probe": "How should the system manage temperature and humidity?"
    },
    # ... 7 more domains
}
```

Each domain entry contains:

| Field            | Purpose                                   | Example                           |
| ---------------- | ----------------------------------------- | --------------------------------- |
| `label`          | Human-readable name                       | "Climate Control"                 |
| `detection_kw`   | Keywords to detect domain mention         | ["temperature", "humidity"]       |
| `exclusion_kw`   | Phrases indicating scope exclusion        | ["no climate", "not climate"]     |
| `fallback_probe` | Fallback question if domain not discussed | "How should the system manage..." |

### 2. **Three-Phase Lifecycle**

#### **Phase 1: Initialization (Before Turn 1)**

- `PromptArchitect` starts with `DEFAULT_DOMAIN_COVERAGE_GATE`

#### **Phase 2: Generation (After Turn 1 — First User Message)**

- **Function**: `generate_domain_gate_from_llm()`
- **Trigger**: First user message received
- **Process**:
  1. Call LLM with project description
  2. LLM generates 5-8 project-specific domains
  3. System merges with defaults as fallback
  4. Result replaces `self._architect.domain_gate`

**Example LLM Input:**

```
Project description: "We need a smart building automation system
for office facilities. Should control lighting, temperature,
and security alarm systems."
```

**Example LLM Output:**

```json
{
  "lighting_control": {
    "label": "Lighting Control",
    "detection_kw": ["lighting", "lights", "brightness", "dimmer"],
    "exclusion_kw": ["no lighting", "lighting excluded"],
    "fallback_probe": "How should the system control office lighting?"
  },
  "temperature_management": {
    "label": "Temperature Management",
    "detection_kw": ["temperature", "hvac", "thermal", "comfort"],
    "exclusion_kw": ["no temperature", "no hvac"],
    "fallback_probe": "What temperature control is needed?"
  },
  "security_systems": {
    "label": "Security Systems",
    "detection_kw": ["security", "alarm", "intrusion", "camera"],
    "exclusion_kw": ["no security"],
    "fallback_probe": "What security features are required?"
  }
}
```

#### **Phase 3: Expansion (After Turn 5)**

- **Function**: `expand_domain_gate_from_llm()`
- **Trigger**: After 5 turns of conversation
- **Process**:
  1. Analyze conversation corpus (all turns 1-5)
  2. Review extracted requirements
  3. Ask LLM: "Should we add new domains?"
  4. Add any recommended domains to gate
  5. Update `self._architect.domain_gate`

**Example Scenario:**

```
Initial domains: [Lighting, Temperature, Security]
Conversation mentions: "We need detailed energy reports"
LLM recommendation: Add "Energy Analytics" domain
Result: [Lighting, Temperature, Security, Energy Analytics]
```

---

## Implementation Details

### Modified Files

#### 1. **`src/components/prompt_architect.py`**

**New Constants:**

```python
DEFAULT_DOMAIN_COVERAGE_GATE: dict[str, dict] = {...}  # 8 smart home domains
```

**New Functions:**

- `generate_domain_gate_from_llm()`: Initial domain generation (turn 1)
- `expand_domain_gate_from_llm()`: Domain expansion evaluation (turn 5)

**Updated `PromptArchitect` Class:**

```python
@dataclass
class PromptArchitect:
    domain_gate: dict[str, dict] = field(
        default_factory=lambda: dict(DEFAULT_DOMAIN_COVERAGE_GATE)
    )

    def _build_context_block(self, state) -> str:
        # Now uses self.domain_gate instead of global DOMAIN_COVERAGE_GATE
        gate_status = compute_domain_gate(state, self.domain_gate)
        ...
```

**Key Changes:**

- `domain_gate` now instance variable (not static)
- `_build_context_block()` moved into class as method
- All helper functions (`compute_domain_gate`, etc.) take `domain_gate` as parameter

#### 2. **`src/components/conversation_manager.py`**

**New Logic in `send_turn()` Method:**

```python
# After turn 1: Generate initial domain gate
if turn.turn_id == 1:
    self._architect.domain_gate = generate_domain_gate_from_llm(
        first_user_message=user_message,
        project_context=state.project_name,
        llm_provider=self.provider,
    )

# After turn 5: Evaluate domain expansion
elif turn.turn_id == 5:
    self._architect.domain_gate = expand_domain_gate_from_llm(
        current_gate=self._architect.domain_gate,
        conversation_corpus=corpus,
        requirements_texts=req_texts,
        llm_provider=self.provider,
    )
```

---

## Workflow Example

### **Conversation Flow**

```
📍 Turn 1 (User)
"I want a smart home system that manages temperature, lighting,
and security. Users should access it via mobile app."

📍 LLM Generation Triggered
→ Generates domain gate (8 domains from project description)
  ✅ Climate Control (detected: "temperature")
  ✅ Security & Alarm (detected: "security")
  ✅ Appliance & Lighting (detected: "lighting")
  ✅ Remote Access (detected: "mobile app")
  🔶 Scheduling & Plans (partial - may be implied)
  ⬜ User Accounts & Roles (unprobed)
  ⬜ Historical Data & Logs (unprobed)
  ⬜ Hardware Connectivity (unprobed)

📍 Turns 2-5 (Elicitation)
LLM probes each domain systematically:
  Turn 2: "Let me ask about Security & Alarm..."
  Turn 3: "Tell me about scheduling requirements..."
  Turn 4: "How should different users access the system?"
  Turn 5: "What data should we store for reporting?"

📍 Turn 5 (Domain Expansion Check)
Corpus Analysis:
  - Mentions: "energy consumption", "reports", "analytics"

LLM Evaluation:
  "Based on energy requirements mentioned, suggest adding:
   - Energy Monitoring & Analytics domain"

Updated Gate: +1 new domain (total: 9)

📍 Turns 6+ (Continue Elicitation)
System explores newly added domains:
  Turn 6: "What energy data should the system track?"
  ...
```

---

## Domain Status Indicators

In the dynamic context shown to the assistant each turn:

```
━━━ DOMAIN COVERAGE GATE  [3/8 — 37%] ━━━
  ✅ Confirmed  🔶 Partial  ⬜ Unprobed  ❌ Excluded

  ✅  Climate Control
  ✅  Security & Alarm
  ✅  Appliance & Lighting
  🔶  Scheduling & Plans
      ↳ Probe: "Should the system support automation routines?"
  ⬜  Remote Access
      ↳ Probe: "How should users interact with the system remotely?"
  ⬜  User Accounts & Roles
      ↳ Probe: "Who needs to access the system?"
  ⬜  Historical Data & Logs
      ↳ Probe: "Should the system store historical data?"
  ⬜  Hardware Connectivity
      ↳ Probe: "What hardware infrastructure will be used?"

⚠️  GATE NOT SATISFIED — Do NOT offer SRS generation yet.
NEXT ACTION: Ask about → Remote Access
USE THIS PROBE: "How should users interact with the system remotely?"
```

---

## Key Features

### ✅ **Dynamic Generation**

- Domain gate is project-specific via LLM
- Not hardcoded to single domain (smart homes)
- Adaptable to any system type

### ✅ **Automatic Expansion**

- Turn 5 checkpoint for new domain discovery
- Avoids premature SRS generation
- Captures emerging requirements

### ✅ **Backward Compatibility**

- Falls back to defaults if LLM fails
- Doesn't break existing workflows
- Transparent to SRSFormatter

### ✅ **Robust Error Handling**

- LLM failures don't crash system
- JSON parsing handles malformed responses
- Graceful degradation to defaults

---

## Integration Points

### **SRSFormatter** (No Changes Required)

- Calls `architect.compute_domain_gate_status(state)`
- Gets current domain gate automatically
- Uses actual domains in SRS document

### **GapDetector** (No Changes Required)

- Works with dynamic domain gate transparently
- References domains from state

### **Elicitation Loop** (Automatic)

- Domain gate drives conversation flow
- Fallback probes dynamically injected
- Phase gates respect domain coverage

---

## Testing the Implementation

### **Manual Test Flow**

1. **Start Session**

   ```python
   manager = ConversationManager(provider=ollama_provider)
   session_id, state, logger, _ = manager.start_session()
   ```

2. **Send First Message** (Triggers Domain Generation)

   ```python
   response1 = manager.send_turn(
       "I need a smart office system for lighting and HVAC.",
       state, logger
   )
   # ✅ Domain gate generated from this message
   ```

3. **Send 5 More Messages** (Turns 2-5)

   ```python
   for i in range(4):
       response = manager.send_turn(user_input, state, logger)
   ```

4. **Monitor Turn 6** (Domain Expansion Checked at Turn 5)

   ```python
   response6 = manager.send_turn(user_input, state, logger)
   # ✅ Domain gate may be expanded based on conversation
   ```

5. **Check Domain Status**
   ```python
   status = manager._architect.compute_domain_gate_status(state)
   # Returns: {"climate_control": "confirmed", ...}
   ```

---

## Fallback Behavior

### **If LLM Generator Fails:**

1. Exception caught and logged
2. System falls back to `DEFAULT_DOMAIN_COVERAGE_GATE`
3. Conversation continues normally
4. Administrator notified in console output

```python
try:
    domain_gate = generate_domain_gate_from_llm(...)
except Exception as e:
    print(f"Warning: Failed to generate domain gate: {e}")
    domain_gate = dict(DEFAULT_DOMAIN_COVERAGE_GATE)  # Fallback
```

### **If JSON Parsing Fails:**

- Regex extracts JSON block from markdown code
- Validates all required keys present
- Falls back if format invalid

---

## Future Enhancements

### **Potential Improvements:**

1. **Domain Suggestions After Every N Turns**
   - Not just turn 5
   - Historical patterns from past projects

2. **Project Type Auto-Detection**
   - Detect "smart home" vs "enterprise software" vs "IoT" automatically
   - Load appropriate domain templates

3. **User-Guided Domain Override**
   - Stakeholder can manually add/remove domains
   - Overrides LLM suggestions

4. **Domain Dependency Tracking**
   - Some domains require others (e.g., scheduling needs user accounts)
   - Auto-confirm dependent domains

5. **Confidence Scoring**
   - LLM provides confidence for each domain
   - Prioritize probing low-confidence domains

---

## Summary

The **Domain Coverage Gate** implementation provides:

| Aspect          | Description                                 |
| --------------- | ------------------------------------------- |
| **Generation**  | LLM-based after first user message          |
| **Expansion**   | Automatic evaluation at turn 5              |
| **Fallback**    | Default 8 smart-home domains if LLM fails   |
| **Integration** | Transparent to SRSFormatter & GapDetector   |
| **Status**      | Real-time tracking shown in dynamic context |
| **Robustness**  | Error handling & graceful degradation       |

This ensures the elicitation process explores ALL relevant system domains before SRS generation, improving requirements completeness and reducing gaps.
