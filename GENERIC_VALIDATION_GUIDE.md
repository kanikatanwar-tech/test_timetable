# Generic Validation Test Scripts - Documentation

## Problem Statement

Previously, test files had hardcoded references to specific teachers, subjects, and classes:
- ❌ `verify_6a_parallels.py` - Only works with 6A/6B parallelism
- ❌ `verify_monika_pjb.py` - Only checks MONIKA's periods
- ❌ `debug_monika_periods.py` - Hardcoded for MONIKA/SKT

**Issue**: These scripts ONLY work for THIS specific school's data. They won't work for ANY other user's timetable.

## Solution

Created THREE new **generic, configuration-driven test scripts** that work with ANY configuration:

---

## New Generic Test Scripts

### 1. `validate_config_generic.py` ⭐ START HERE

**Purpose**: Comprehensive validation of ANY timetable configuration.

**Features**:
- ✅ Works with ANY number of teachers, classes, subjects
- ✅ Loads configuration from `TimetableConfigs/step1.json|2|3`
- ✅ 7 validation checks (configuration, structure, parallels, combines, workload, coverage, conflicts)
- ✅ Reports summary of what was configured
- ✅ Reports what was validated

**Usage**:
```bash
cd timetable_app/test
python validate_config_generic.py
```

**Output**: 
```
📂 Loading configs from: ...

CONFIGURATION SUMMARY
==================
Step 1: 15 teachers, 5 working days, 6 periods/day
Step 2: 20 classes, 45 subjects, 3 with parallels
Step 3: 5 combined groups, 2 unavailable teachers

⚙️ Generating timetable...
✅ Timetable generated successfully!

RUNNING GENERIC TIMETABLE VALIDATION
✅ Configuration validity
✅ Basic structure
✅ Parallel teachers validation
✅ Combined classes validation
✅ Teacher period counts
✅ All classes scheduled
✅ No conflicts

Results: 7 passed, 0 failed
```

---

### 2. `validate_parallel_generic.py`

**Purpose**: Validate that ALL parallel teachers get their assigned periods.

**Features**:
- ✅ Auto-discovers ALL parallel assignments from configuration
- ✅ For EACH parallel teacher and subject, counts actual periods
- ✅ Verifies count matches expected (same as primary teacher)
- ✅ Works with 2, 3, 5, or ANY number of parallel teachers
- ✅ Works with ANY class names, ANY subject names

**Usage**:
```bash
cd timetable_app/test
python validate_parallel_generic.py
```

**Output** (example for YOUR data):
```
VALIDATING PARALLEL TEACHERS
════════════════════════════════════════════════════════════════════════════════

📚 Class: 6A, Primary Subject: SKT
   Primary Teacher: ANITA KUMARI (6 periods)
   Parallel Teachers:
      1. URDU → IRFAN
         ✅ IRFAN has 6 periods (expected 6) — CORRECT
      2. PJB → MONIKA
         ✅ MONIKA has 6 periods (expected 6) — CORRECT

📚 Class: 7B, Primary Subject: SKT
   Primary Teacher: NEHA (5 periods)
   Parallel Teachers:
      1. URDU → IRFAN
         ✅ IRFAN has 5 periods (expected 5) — CORRECT

TEACHER SUMMARY
════════════════════════════════════════════════════════════════════════════════
  ANITA KUMARI: 11 periods → SKT(11)
  IRFAN: 11 periods → URDU(11)
  MONIKA: 6 periods → PJB(6)
  NEHA: 10 periods → SKT(10)
  ...

✅ ALL PARALLEL TEACHERS VALIDATED — All periods correct!
```

---

### 3. `validate_combined_generic.py`

**Purpose**: Validate that combined classes are scheduled at the SAME time slots.

**Features**:
- ✅ Auto-discovers ALL combined class groups from step3 config
- ✅ For EACH combined group and subject, checks slots match
- ✅ Verifies all classes in group have same (day, period) slots
- ✅ Works with ANY class names (6A, 6B, 6C, Class-1, etc.)
- ✅ Works with ANY number of combined classes

**Usage**:
```bash
cd timetable_app/test
python validate_combined_generic.py
```

**Output** (example):
```
VALIDATING COMBINED CLASSES
════════════════════════════════════════════════════════════════════════════════

📚 Combined Group: 6A + 6B + 6C, Subject: Math
   • 6A: 6 periods for Math
      ✅ 6B has SAME slots as 6A — CORRECT
      ✅ 6C has SAME slots as 6A — CORRECT

📚 Combined Group: 7A + 7B, Subject: Science
   • 7A: 4 periods for Science
      ✅ 7B has SAME slots as 7A — CORRECT

✅ ALL COMBINED CLASSES VALIDATED — All groups scheduled together correctly!
```

---

## Why These Are "Generic"

### Example 1: Your Current Configuration
```
Teachers: ANITA KUMARI, IRFAN, MONIKA
Classes: 6A, 6B, 7B
Parallels: 6A SKT/URDU/PJB
Combines: 6A+6B for SKT
```

Script Output:
```
✅ ANITA KUMARI (parallel teacher for SKT): 6 periods
✅ IRFAN (parallel teacher for URDU): 6 periods
✅ MONIKA (parallel teacher for PJB): 6 periods
✅ 6A+6B scheduled together for SKT
```

### Example 2: Different School Configuration
```
Teachers: Mr. A, Mr. B, Mr. C, Miss D
Classes: 10-A, 10-B, 11-A
Parallels: 10-A Hindi/Marathi, 11-A Physics/Lab
Combines: 10-A+10-B for Hindi
```

Script Output (SAME CODE):
```
✅ Mr. B (parallel teacher for Marathi): 5 periods
✅ Miss D (parallel teacher for Lab): 6 periods
✅ 10-A+10-B scheduled together for Hindi
```

**The scripts don't change!** They auto-discover and validate whatever is in the config.

---

## How They Work: The Generic Pattern

### Pattern 1: Auto-Discovery
```python
# DON'T hardcode specific names
# DO discover from configuration

# ❌ WRONG
for teacher in ['MONIKA', 'IRFAN', 'ANITA KUMARI']:
    validate_teacher(teacher)

# ✅ RIGHT
for class_name, class_data in step2.items():
    for subject in class_data['subjects']:
        for par in subject.get('parallel_subjects', []):
            teacher = par['teacher']  # Whatever name is in config
            validate_teacher(teacher)
```

### Pattern 2: Configuration-Driven Logic
```python
# ❌ WRONG
if class_name.startswith('6'):  # Hardcoded class logic

# ✅ RIGHT
for class_name in step2.keys():  # Use whatever classes exist
    validate_class(class_name)
```

### Pattern 3: Iterate Over Config, Not Hard Values
```python
# ❌ WRONG
class_list = ['6A', '6B', '6C', '7A', '7B', '7C']

# ✅ RIGHT
class_list = list(step2.keys())  # Whatever classes exist
```

---

## How to Use These Scripts

### Step 1: Prepare Your Configuration

Place your configs in `timetable_app/TimetableConfigs/`:
```
TimetableConfigs/
  ├── step1.json    (Basic settings)
  ├── step2.json    (Class & subject assignments)
  └── step3.json    (Constraints & combines)
```

### Step 2: Run Validation

```bash
cd timetable_app/test

# Comprehensive validation (recommended - run this first)
python validate_config_generic.py

# Detailed parallel teacher check
python validate_parallel_generic.py

# Detailed combined class check
python validate_combined_generic.py
```

### Step 3: Review Results

The scripts will:
1. Load your configuration automatically
2. Generate the timetable
3. Run validation checks
4. Report ✅ for what passed and ❌ for what failed

---

## Benefits Over Old Test Files

| Aspect | Old Files | New Generic |
|--------|-----------|------------|
| **Works with any teachers?** | ❌ No (hardcoded names) | ✅ Yes (config-driven) |
| **Works with any classes?** | ❌ No (hardcoded 6A/6B) | ✅ Yes (config-driven) |
| **Works with any subjects?** | ❌ No (hardcoded SKT/URDU/PJB) | ✅ Yes (config-driven) |
| **Discovers parallels auto?** | ❌ Manual list | ✅ Auto from config |
| **Discovers combines auto?** | ❌ Manual list | ✅ Auto from config |
| **Requires code changes for new config?** | ❌ Yes | ✅ No |
| **Works for other users unchanged?** | ❌ No | ✅ Yes |

---

## When to Use Each Script

### `validate_config_generic.py` - General Purpose
**Use when**:
- First-time generation validation
- After making config changes
- Before downloading Excel files
- General health check
- Quick overview of what was configured

### `validate_parallel_generic.py` - Parallel Focus
**Use when**:
- You have parallel teachers and want detailed validation
- Need to confirm each parallel teacher got their full periods
- Debugging parallel teacher issues
- Want to see period count breakdown

### `validate_combined_generic.py` - Combined Focus
**Use when**:
- You have combined classes and want detailed validation
- Need to confirm combined classes scheduled together
- Debugging combine synchronization issues
- Want to verify all classes in group have identical slots

---

## Architecture: How Scripts Are Generic

### Key Principle: Configuration-Driven vs. Hardcoded

**All three scripts follow this pattern:**

1. **Load Configuration** (GENERIC - works for any config)
   ```python
   step1, step2, step3 = load_configs(config_dir)
   ```

2. **Discover What Exists** (GENERIC - auto-discovers from config)
   ```python
   parallel_teachers = find_all_parallel_assignments(step2)
   combined_groups = find_all_combines(step3)
   ```

3. **Validate Against Discovery** (GENERIC - validates what was found)
   ```python
   for teacher in discovered_parallel_teachers:
       validate_teacher_has_periods(teacher)
   ```

4. **Report Results** (GENERIC - shows what was validated)
   ```python
   Print: "Teacher X: Y periods (expected Y) — CORRECT"
   ```

**Result**: Same code validates MONIKA in YOUR config and MR. SHARMA in someone else's config.

---

## Next Steps

1. ✅ **Understand** the architecture principles (see `ARCHITECTURE_PRINCIPLES.md`)
2. ✅ **Run** the generic validation scripts
3. ✅ **Review** the output to verify your configuration is correct
4. ✅ **Use** as template for any custom validation needs

---

## FAQ

**Q: Why do we need scripts if the generator handles everything?**

A: The generator creates the timetable. The scripts **verify** that the timetable is correctly representing your configuration. They catch issues like:
- Parallel teacher missing periods
- Combined classes not scheduled together
- Class teacher not assigned to right period
- Workload discrepancies

**Q: Can I modify these scripts?**

A: Yes! They're templates. You can:
- Add more validation checks
- Add custom reporting
- Export to Excel/PDF
- Integrate with your own workflow

Just follow the **generic pattern**: Read from config, don't hardcode.

**Q: What if I have a custom constraint?**

A: Add it to the `GenericTimetableValidator` class in `validate_config_generic.py`. Follow the same pattern:
```python
def check_my_custom_constraint(self) -> bool:
    """Check something specific to your school."""
    custom_config = self.step3.get('my_custom_constraint', {})
    # Use custom_config values, don't hardcode
    # Report errors/warnings
    return True or False
```

---

## Summary

✅ **Old approach**: Scripts specific to YOUR data
❌ **New approach**: Scripts that work with ANY data

✅ **Generic scripts** let other users validate their configs without code changes
✅ **Same code** handles 2 parallel teachers, 5 parallel teachers, ANY teachers
✅ **Configuration-driven** = scalable, maintainable, universal
