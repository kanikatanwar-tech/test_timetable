"""
Generic Parallel Teacher Validation

This script validates that ALL parallel teachers get correct periods.
Works with ANY configuration (6A, 7B, 10C, ANY classes with ANY parallel subjects).

NOT hardcoded for specific teachers/subjects like MONIKA/SKT/URDU.
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


def find_all_parallel_assignments(step2_config: dict):
    """
    Find ALL parallel subject assignments across all classes.
    
    Returns list of:
    {
        'class': '6A',
        'primary_subject': 'Math',
        'primary_teacher': 'Mrs. A',
        'primary_periods': 5,
        'parallel': [
            {'subject': 'Science', 'teacher': 'Mr. B'},
            {'subject': 'Hindi', 'teacher': 'Mrs. C'}
        ]
    }
    """
    parallel_assignments = []
    
    for class_name, class_data in step2_config.items():
        for subject in class_data.get('subjects', []):
            par_subjects = subject.get('parallel_subjects', [])
            if par_subjects:
                parallel_assignments.append({
                    'class': class_name,
                    'primary_subject': subject['name'],
                    'primary_teacher': subject['teacher'],
                    'primary_periods': subject.get('periods', 0),
                    'parallel': par_subjects
                })
    
    return parallel_assignments


def validate_parallel_teachers_get_periods(engine, config, parallel_assignments):
    """
    Validate that each parallel teacher has correct period count for their subject.
    """
    print("\n" + "="*80)
    print("VALIDATING PARALLEL TEACHERS")
    print("="*80)
    
    if not parallel_assignments:
        print("\n✓ No parallel subjects configured — validation skipped.")
        return True
    
    all_passed = True
    
    for pa in parallel_assignments:
        class_name = pa['class']
        primary_subj = pa['primary_subject']
        
        print(f"\n📚 Class: {class_name}, Primary Subject: {primary_subj}")
        print(f"   Primary Teacher: {pa['primary_teacher']} ({pa['primary_periods']} periods)")
        print(f"   Parallel Teachers:")
        
        for i, par in enumerate(pa['parallel'], 1):
            teacher_name = par['teacher']
            subject_name = par['subject']
            
            print(f"      {i}. {subject_name} → {teacher_name}")
            
            # Count periods for this parallel teacher in this subject for this class
            period_count = count_teacher_periods(engine, teacher_name, subject_name, class_name)
            
            # Expected: same as primary teacher periods (they teach same class at same time)
            expected = pa['primary_periods']
            
            if period_count == expected:
                print(f"         ✅ {teacher_name} has {period_count} periods (expected {expected}) — CORRECT")
            else:
                print(f"         ❌ {teacher_name} has {period_count} periods (expected {expected}) — WRONG!")
                all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL PARALLEL TEACHERS VALIDATED — All periods correct!")
    else:
        print("❌ VALIDATION FAILED — Some parallel teachers missing periods!")
    print("="*80)
    
    return all_passed


def count_teacher_periods(engine, teacher_name: str, subject_name: str, class_name: str = None):
    """
    Count how many periods this teacher has for this subject.
    If class_name specified, count only in that class.
    If class_name is None, count across ALL classes.
    """
    count = 0
    
    if not hasattr(engine, '_timetable') or not engine._timetable:
        return 0
    
    for day_idx, day_tt in enumerate(engine._timetable.get('class_timetable', {}).get(class_name or '*', {})):
        # Iterate through all classes if class_name is None
        pass
    
    # Simpler approach: use teacher grid if available
    if hasattr(engine, '_timetable') and engine._timetable:
        teacher_grid = engine._timetable.get('teacher_timetable', {})
        
        if teacher_name in teacher_grid:
            for day_periods in teacher_grid[teacher_name]:
                for cell in day_periods:
                    if cell is None:
                        continue
                    
                    cell_subject = cell.get('subject', '')
                    cell_class = cell.get('class', '')
                    
                    # Match on subject and optionally on class
                    if cell_subject == subject_name:
                        if class_name is None or cell_class == class_name:
                            count += 1
    
    return count


def print_summary(engine, step2_config, step1_config):
    """Print summary of all teachers and their period counts."""
    print("\n" + "="*80)
    print("TEACHER SUMMARY")
    print("="*80 + "\n")
    
    teacher_names = sorted(step1_config.get('teacher_names', []))
    
    if not hasattr(engine, '_timetable') or not engine._timetable:
        print("⚠ No timetable generated yet.")
        return
    
    teacher_grid = engine._timetable.get('teacher_timetable', {})
    
    for teacher_name in teacher_names:
        if teacher_name not in teacher_grid:
            print(f"  {teacher_name}: 0 periods (not used)")
            continue
        
        # Count total periods
        total_periods = 0
        subjects_taught = {}
        
        for day_periods in teacher_grid[teacher_name]:
            for cell in day_periods:
                if cell is None:
                    continue
                total_periods += 1
                subject = cell.get('subject', 'Unknown')
                subjects_taught[subject] = subjects_taught.get(subject, 0) + 1
        
        if total_periods > 0:
            subjects_str = ", ".join([f"{s}({c})" for s, c in sorted(subjects_taught.items())])
            print(f"  {teacher_name}: {total_periods} periods → {subjects_str}")
        else:
            print(f"  {teacher_name}: 0 periods (not used)")
    
    print("\n" + "="*80)


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
    
    # Find all parallel assignments in the configuration
    parallel_assignments = find_all_parallel_assignments(step2)
    
    if not parallel_assignments:
        print("\n⚠ No parallel subjects found in configuration.")
        print_summary(engine, step2, step1)
        return True
    
    print(f"\n📊 Found {len(parallel_assignments)} class(es) with parallel subjects:")
    for pa in parallel_assignments:
        print(f"   • {pa['class']}: {pa['primary_subject']} → {len(pa['parallel'])} parallel subject(s)")
    
    # Validate all parallel teachers
    is_valid = validate_parallel_teachers_get_periods(engine, step1, parallel_assignments)
    
    # Print summary
    print_summary(engine, step2, step1)
    
    return is_valid


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
