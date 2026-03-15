"""
Generic Combined Classes Validation

This script validates that combined classes are correctly scheduled together.
Works with ANY classes, ANY subjects, ANY combinations.

NOT hardcoded for "6A+6B" or specific classes.
"""

import json
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generator import TimetableEngine


def load_configs(config_dir: str):
    """Load all 3 step configs from directory."""
    config_dir = Path(config_dir)
    
    step1 = json.loads((config_dir / "step1.json").read_text())
    step2 = json.loads((config_dir / "step2.json").read_text())
    step3 = json.loads((config_dir / "step3.json").read_text())
    
    return step1, step2, step3


def find_all_combines(step3_config: dict):
    """
    Find ALL combined class groups from step3 configuration.
    
    Returns list of:
    {
        'primary_class': '6A',
        'subject': 'Math',
        'combined_group': ['6A', '6B', '6C']
    }
    """
    combines = step3_config.get('combines', {})
    combine_list = []
    
    for class_name, subject_combines in combines.items():
        for subject, combined_classes in subject_combines.items():
            combine_list.append({
                'primary_class': class_name,
                'subject': subject,
                'combined_group': combined_classes,
                'is_bidirectional': True  # Should be synchronized across all classes
            })
    
    return combine_list


def validate_combined_classes_scheduled_together(engine, combines):
    """
    Validate that all classes in a combined group have the SAME periods for the combined subject.
    """
    print("\n" + "="*80)
    print("VALIDATING COMBINED CLASSES")
    print("="*80)
    
    if not combines:
        print("\n✓ No combined classes configured — validation skipped.")
        return True
    
    all_passed = True
    
    if not hasattr(engine, '_timetable') or not engine._timetable:
        print("⚠ No timetable generated yet.")
        return False
    
    class_tt = engine._timetable.get('class_timetable', {})
    
    for combine in combines:
        primary = combine['primary_class']
        subject = combine['subject']
        group = combine['combined_group']
        
        print(f"\n📚 Combined Group: {' + '.join(group)}, Subject: {subject}")
        
        # Get period slots for each class in the group
        period_slots = {}
        for class_name in group:
            if class_name not in class_tt:
                print(f"   ⚠ {class_name} not found in timetable!")
                all_passed = False
                continue
            
            slots = []
            for day_idx, day_periods in enumerate(class_tt[class_name]):
                for period_idx, cell in enumerate(day_periods):
                    if cell is None:
                        continue
                    
                    # Check if this cell is for the combined subject
                    cell_subject = cell.get('subject', '')
                    if cell_subject == subject:
                        slots.append({
                            'day': day_idx,
                            'period': period_idx,
                            'teacher': cell.get('teacher', ''),
                            'cell_key': (day_idx, period_idx)
                        })
            
            period_slots[class_name] = slots
            print(f"   • {class_name}: {len(slots)} periods for {subject}")
        
        # Verify all classes have same slots
        if not period_slots:
            print(f"   ❌ No slots found for {subject}!")
            all_passed = False
            continue
        
        first_class = group[0]
        first_slots = period_slots.get(first_class, [])
        first_slot_keys = set(s['cell_key'] for s in first_slots)
        
        for other_class in group[1:]:
            other_slots = period_slots.get(other_class, [])
            other_slot_keys = set(s['cell_key'] for s in other_slots)
            
            if first_slot_keys == other_slot_keys and len(first_slot_keys) > 0:
                print(f"      ✅ {other_class} has SAME slots as {first_class} — CORRECT")
            else:
                print(f"      ❌ {other_class} has DIFFERENT slots than {first_class} — WRONG!")
                print(f"         {first_class} slots: {first_slots}")
                print(f"         {other_class} slots: {other_slots}")
                all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL COMBINED CLASSES VALIDATED — All groups scheduled together correctly!")
    else:
        print("❌ VALIDATION FAILED — Some combined classes not scheduled together!")
    print("="*80)
    
    return all_passed


def print_all_combines(combines, step2_config):
    """Print all combines found in configuration."""
    print("\n📊 Combined Class Groups Found:")
    print("="*80)
    
    if not combines:
        print("No combined classes configured.")
        return
    
    # Group by combined_group to avoid duplicates
    seen_groups = set()
    for combine in combines:
        group_key = tuple(sorted(combine['combined_group']))
        if group_key not in seen_groups:
            print(f"\n  Class Group: {' + '.join(group_key)}")
            # Find all subjects combined in this group
            subjects_in_group = [c['subject'] for c in combines 
                               if tuple(sorted(c['combined_group'])) == group_key]
            print(f"  Subjects: {', '.join(subjects_in_group)}")
            seen_groups.add(group_key)


def main():
    """Main validation script."""
    
    # Load configs
    config_dir = Path(__file__).parent.parent / "TimetableConfigs"
    
    if not config_dir.exists():
        print(f"❌ Config directory not found: {config_dir}")
        return False
    
    print(f"📂 Loading configs from: {config_dir}")
    
    try:
        step1, step2, step3 = load_configs(config_dir)
    except FileNotFoundError as e:
        print(f"❌ Missing config file: {e}")
        return False
    
    # Create engine and generate timetable
    print("\n⚙️  Generating timetable...")
    engine = TimetableEngine()
    engine.configuration = step1
    engine.class_config_data = step2
    engine.step3_data = step3
    
    result = engine.run_full_generation()
    
    if not result.get('ok'):
        print(f"❌ Generation failed: {result.get('message', 'Unknown error')}")
        return False
    
    print("✅ Timetable generation successful!")
    
    # Find all combines in the configuration
    combines = find_all_combines(step3)
    
    if not combines:
        print("\n⚠ No combined classes found in configuration.")
        return True
    
    print(f"\n📊 Found {len(combines)} combine directive(s) in configuration")
    print_all_combines(combines, step2)
    
    # Validate all combined classes
    is_valid = validate_combined_classes_scheduled_together(engine, combines)
    
    return is_valid


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
