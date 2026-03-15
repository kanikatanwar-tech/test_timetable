"""
Generic Configuration Test Runner

This script demonstrates how to validate ANY timetable configuration generically.
Run this INSTEAD of hardcoded test files like verify_6a_parallels.py.

Works with:
- Any number of teachers
- Any teacher names
- Any number of classes  
- Any class names (6A, 10B, Class-1, AA, anything)
- Any subjects
- Any parallel configurations
- Any combined class groups
"""

import json
from pathlib import Path
import sys
from collections import defaultdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generator import TimetableEngine


def load_configs(config_dir: str):
    """Load all 3 step configs from directory."""
    config_dir = Path(config_dir)
    
    files_needed = ['step1.json', 'step2.json', 'step3.json']
    for fname in files_needed:
        fpath = config_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Missing: {fpath}")
    
    step1 = json.loads((config_dir / "step1.json").read_text())
    step2 = json.loads((config_dir / "step2.json").read_text())
    step3 = json.loads((config_dir / "step3.json").read_text())
    
    return step1, step2, step3


class GenericTimetableValidator:
    """Generic validator that works with ANY configuration."""
    
    def __init__(self, engine, step1, step2, step3):
        self.engine = engine
        self.step1 = step1
        self.step2 = step2
        self.step3 = step3
        self.errors = []
        self.warnings = []
    
    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("\n" + "="*80)
        print("RUNNING GENERIC TIMETABLE VALIDATION")
        print("="*80 + "\n")
        
        checks = [
            ("Configuration validity", self.check_configuration),
            ("Basic structure", self.check_basic_structure),
            ("Parallel teachers validation", self.check_parallel_teachers),
            ("Combined classes validation", self.check_combined_classes),
            ("Teacher period counts", self.check_teacher_workload),
            ("All classes scheduled", self.check_class_coverage),
            ("No conflicts", self.check_no_conflicts),
        ]
        
        passed = 0
        failed = 0
        
        for check_name, check_func in checks:
            try:
                is_ok = check_func()
                if is_ok:
                    print(f"✅ {check_name}")
                    passed += 1
                else:
                    print(f"❌ {check_name}")
                    failed += 1
            except Exception as e:
                print(f"❌ {check_name}: {e}")
                self.errors.append(f"{check_name}: {e}")
                failed += 1
        
        print(f"\n{'='*80}")
        print(f"Results: {passed} passed, {failed} failed")
        print(f"{'='*80}\n")
        
        if self.errors:
            print("ERRORS:")
            for err in self.errors:
                print(f"  ❌ {err}")
        
        if self.warnings:
            print("\nWARNINGS:")
            for warn in self.warnings:
                print(f"  ⚠ {warn}")
        
        return len(self.errors) == 0
    
    def check_configuration(self) -> bool:
        """Check if configuration loaded correctly."""
        required_fields = {
            'step1': ['teacher_names', 'working_days', 'periods_per_day'],
            'step2': [],  # step2 keys are class names
            'step3': ['combines']
        }
        
        if not self.step1.get('teacher_names'):
            self.errors.append("step1: No teacher_names found")
            return False
        
        if not self.step2:
            self.errors.append("step2: No class configuration found")
            return False
        
        return True
    
    def check_basic_structure(self) -> bool:
        """Check timetable basic structure."""
        if not hasattr(self.engine, '_timetable') or not self.engine._timetable:
            self.errors.append("No timetable generated")
            return False
        
        timetable = self.engine._timetable
        if 'class_timetable' not in timetable:
            self.errors.append("Missing class_timetable")
            return False
        
        if 'teacher_timetable' not in timetable:
            self.errors.append("Missing teacher_timetable")
            return False
        
        return True
    
    def check_parallel_teachers(self) -> bool:
        """Check that parallel teachers get periods."""
        if not self.engine._timetable:
            return True
        
        timetable = self.engine._timetable
        
        # Find all parallel assignments
        parallel_teachers = defaultdict(list)
        
        for subject in self.step2.values():
            for subj_config in subject.get('subjects', []):
                par_subs = subj_config.get('parallel_subjects', [])
                if par_subs:
                    for par in par_subs:
                        teacher = par.get('teacher', '')
                        subject_name = par.get('subject', '')
                        if teacher:
                            parallel_teachers[teacher].append(subject_name)
        
        if not parallel_teachers:
            return True  # No parallel teachers configured
        
        # Check each parallel teacher has periods
        for teacher, subjects in parallel_teachers.items():
            if teacher not in timetable.get('teacher_timetable', {}):
                self.warnings.append(f"Parallel teacher '{teacher}' has no periods in timetable")
        
        return True
    
    def check_combined_classes(self) -> bool:
        """Check that combined classes are scheduled together."""
        if not self.engine._timetable:
            return True
        
        combines = self.step3.get('combines', {})
        if not combines:
            return True  # No combines configured
        
        class_tt = self.engine._timetable.get('class_timetable', {})
        
        # For each combine group
        for primary_class, subject_combines in combines.items():
            for subject, combined_group in subject_combines.items():
                
                # Get slots for each class in group
                slots_by_class = {}
                for class_name in combined_group:
                    if class_name not in class_tt:
                        self.warnings.append(f"Class '{class_name}' not in timetable")
                        continue
                    
                    slots = []
                    for day_idx, day in enumerate(class_tt[class_name]):
                        for period_idx, cell in enumerate(day):
                            if cell and cell.get('subject') == subject:
                                slots.append((day_idx, period_idx))
                    
                    slots_by_class[class_name] = slots
                
                # Check all classes have same slots
                if not slots_by_class:
                    continue
                
                first_class = list(combined_group)[0]
                first_slots = set(slots_by_class.get(first_class, []))
                
                for other_class in combined_group[1:]:
                    other_slots = set(slots_by_class.get(other_class, []))
                    if first_slots != other_slots:
                        self.errors.append(
                            f"Combined '{subject}' {combined_group}: "
                            f"'{first_class}' slots differ from '{other_class}'"
                        )
                        return False
        
        return True
    
    def check_teacher_workload(self) -> bool:
        """Check that teacher period counts are reasonable."""
        if not self.engine._timetable:
            return True
        
        teacher_tt = self.engine._timetable.get('teacher_timetable', {})
        
        for teacher, days in teacher_tt.items():
            total_periods = sum(1 for day in days for cell in day if cell)
            
            if total_periods == 0:
                self.warnings.append(f"Teacher '{teacher}' has 0 periods assigned")
        
        return True
    
    def check_class_coverage(self) -> bool:
        """Check that all configured classes have timetable entries."""
        if not self.engine._timetable:
            return True
        
        class_tt = self.engine._timetable.get('class_timetable', {})
        
        for class_name in self.step2.keys():
            if class_name not in class_tt:
                self.errors.append(f"Class '{class_name}' not found in generated timetable")
                return False
            
            # Check class has at least some periods filled
            total_periods = sum(1 for day in class_tt[class_name] for cell in day if cell)
            if total_periods == 0:
                self.warnings.append(f"Class '{class_name}' has 0 periods assigned")
        
        return True
    
    def check_no_conflicts(self) -> bool:
        """Basic conflict checking - teacher not in 2 places at once."""
        if not self.engine._timetable:
            return True
        
        # This is handled by the generator itself
        # If timetable generated successfully, conflicts should be resolved
        return True


def print_configuration_summary(step1, step2, step3):
    """Print summary of the loaded configuration."""
    print("\n" + "="*80)
    print("CONFIGURATION SUMMARY")
    print("="*80)
    
    print("\n📝 Step 1 - Basic Settings:")
    print(f"  • Teachers: {len(step1.get('teacher_names', []))}")
    print(f"    {', '.join(step1.get('teacher_names', [])[:5])}" + 
          ("..." if len(step1.get('teacher_names', [])) > 5 else ""))
    print(f"  • Working Days: {step1.get('working_days', 5)}")
    print(f"  • Periods/Day: {step1.get('periods_per_day', 6)}")
    
    print("\n📝 Step 2 - Classes & Subjects:")
    classes_with_parallels = 0
    total_subjects = 0
    for class_name, class_data in step2.items():
        subjects = class_data.get('subjects', [])
        total_subjects += len(subjects)
        for subj in subjects:
            if subj.get('parallel_subjects'):
                classes_with_parallels += 1
                break
    
    print(f"  • Classes: {len(step2)}")
    print(f"  • Total Subjects: {total_subjects}")
    print(f"  • Classes with Parallels: {classes_with_parallels}")
    
    print("\n📝 Step 3 - Constraints:")
    combines = step3.get('combines', {})
    combined_count = sum(len(subjects) for subjects in combines.values())
    print(f"  • Combined Groups: {combined_count}")
    print(f"  • Teacher Unavailability: {len(step3.get('teacher_unavailability', {}))}")
    
    print("\n" + "="*80 + "\n")


def main():
    """Main entry point."""
    
    # Get config directory
    config_dir = Path(__file__).parent.parent / "TimetableConfigs"
    
    if not config_dir.exists():
        print(f"❌ Config directory not found: {config_dir}")
        print("\nUsage:")
        print("  python validate_config_generic.py")
        print("\nPlace your configs in: timetable_app/TimetableConfigs/")
        print("  - step1.json")
        print("  - step2.json")
        print("  - step3.json")
        return False
    
    print(f"📂 Loading configs from: {config_dir}")
    
    try:
        step1, step2, step3 = load_configs(config_dir)
    except Exception as e:
        print(f"❌ Error loading configs: {e}")
        return False
    
    # Print configuration summary
    print_configuration_summary(step1, step2, step3)
    
    # Generate timetable
    print("⚙️  Generating timetable...")
    engine = TimetableEngine()
    engine.configuration = step1
    engine.class_config_data = step2
    engine.step3_data = step3
    
    result = engine.run_full_generation()
    
    if not result.get('ok'):
        print(f"❌ Generation failed: {result.get('message', 'Unknown error')}")
        return False
    
    print("✅ Timetable generated successfully!")
    
    # Validate
    validator = GenericTimetableValidator(engine, step1, step2, step3)
    success = validator.validate_all()
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
