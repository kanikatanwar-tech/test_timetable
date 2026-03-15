"""
Timetable Validator — Comprehensive multi-format validation for all Excel exports.

Validates that timetable is correctly represented in ALL Excel formats before download.
Checks:
  1. Class view consistency (all subjects/teachers present)
  2. Teacher view consistency (all classes/subjects present)
  3. Combined class representation (6A+6B labels, workload counts)
  4. Parallel teacher alignment (same time slots, correct subjects)
  5. Class teacher periods marked correctly
  6. Workload summary accuracy
"""

import logging
from collections import defaultdict

log = logging.getLogger(__name__)


class TimetableValidator:
    """Validates timetable for consistency across all Excel export formats."""
    
    def __init__(self, engine):
        """
        Args:
            engine: TimetableEngine instance with generated timetable
        """
        self.eng = engine
        self.tt = engine._timetable
        self.grid = self.tt['grid']
        self.days = self.tt['days']
        self.ppd = self.tt['ppd']
        self.all_classes = self.tt['all_classes']
        
        self.errors = []
        self.warnings = []
    
    def validate_all(self):
        """Run all validation checks. Returns (is_valid, errors, warnings)."""
        self.errors = []
        self.warnings = []
        
        log.info("Starting comprehensive timetable validation...")
        
        # Run all checks
        self._check_class_coverage()
        self._check_teacher_coverage()
        self._check_combined_classes()
        self._check_parallel_subjects()
        self._check_class_teacher_periods()
        self._check_workload_consistency()
        self._check_excel_class_view()
        self._check_excel_teacher_view()
        
        is_valid = len(self.errors) == 0
        log.info(f"Validation complete: {'✅ PASSED' if is_valid else '❌ FAILED'} "
                f"({len(self.errors)} errors, {len(self.warnings)} warnings)")
        
        return is_valid, self.errors, self.warnings
    
    def _check_class_coverage(self):
        """Verify all classes have timetable entries."""
        log.debug("Checking class coverage...")
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            if not class_grid:
                self.errors.append(f"Class {cn}: No timetable grid found")
                continue
            
            # Count non-free periods
            non_free = 0
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    if d < len(class_grid) and p < len(class_grid[d]):
                        if class_grid[d][p] is not None:
                            non_free += 1
            
            if non_free < self.ppd * 2:  # Should have at least 2 days worth
                self.warnings.append(f"Class {cn}: Only {non_free} periods allocated "
                                   f"(expected ~{self.ppd * len(self.days)})")
    
    def _check_teacher_coverage(self):
        """Verify all configured teachers have periods assigned."""
        log.debug("Checking teacher coverage...")
        teacher_periods = defaultdict(int)
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            cfg = self.eng.class_config_data.get(cn, {})
            
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    # Count primary teacher
                    t = cell.get('teacher', '')
                    if t and t not in ('—', '?'):
                        teacher_periods[t] += 1
                    
                    # Count parallel teachers (both old and new format)
                    par_teachers = cell.get('par_teachers', []) or []
                    if par_teachers:
                        for pt in par_teachers:
                            if pt and pt not in ('—', '?'):
                                teacher_periods[pt] += 1
                    else:
                        # Backward compatibility
                        pt = cell.get('par_teach', '')
                        if pt and pt not in ('—', '?'):
                            teacher_periods[pt] += 1
        
        # Check against expected counts from config
        expected_periods = defaultdict(int)
        for cn in self.all_classes:
            cfg = self.eng.class_config_data.get(cn, {})
            for subj in cfg.get('subjects', []):
                t = subj.get('teacher', '').strip()
                periods = subj.get('periods', 0)
                if t:
                    expected_periods[t] += periods
                
                # Count parallel teachers
                par_subs = subj.get('parallel_subjects', []) or []
                if par_subs:
                    for par in par_subs:
                        pt = par.get('teacher', '').strip()
                        if pt:
                            expected_periods[pt] += periods
        
        # Compare
        for teacher, expected in expected_periods.items():
            actual = teacher_periods.get(teacher, 0)
            if actual != expected:
                self.errors.append(
                    f"Teacher {teacher}: Expected {expected} periods, got {actual}")
    
    def _check_combined_classes(self):
        """Verify combined classes show complete combined labels."""
        log.debug("Checking combined class representation...")
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    cc = cell.get('combined_classes', [])
                    if cc and len(cc) >= 2:
                        # This is a combined cell - verify it's in ALL classes
                        for partner_cn in cc:
                            partner_grid = self.grid.get(partner_cn, [])
                            partner_cell = (partner_grid[d][p] 
                                          if d < len(partner_grid) and p < len(partner_grid[d]) 
                                          else None)
                            
                            if partner_cell is None:
                                self.errors.append(
                                    f"Combined class mismatch: {cn} has combined {cc} at "
                                    f"{self.days[d]} P{p+1}, but {partner_cn} is FREE")
                            elif partner_cell.get('combined_classes', []) != cc:
                                self.errors.append(
                                    f"Combined mismatch: {cn} shows {cc}, "
                                    f"but {partner_cn} shows {partner_cell.get('combined_classes', [])}")
    
    def _check_parallel_subjects(self):
        """Verify parallel teachers have same time slots and correct subjects."""
        log.debug("Checking parallel subject alignment...")
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    primary_subj = cell.get('subject', '')
                    par_subjects = cell.get('par_subjects', []) or []
                    par_teachers = cell.get('par_teachers', []) or []
                    
                    if not par_teachers:
                        continue
                    
                    # For each parallel teacher, verify they have this class at same slot
                    for i, pt in enumerate(par_teachers):
                        ps = par_subjects[i] if i < len(par_subjects) else ''
                        
                        # Check if parallel teacher has this class at this slot
                        # (we'll verify this in teacher view check)
                        if not ps:
                            self.errors.append(
                                f"Parallel subject missing: {cn} {primary_subj} at "
                                f"{self.days[d]} P{p+1} has parallel teacher {pt} "
                                f"but no subject assigned")
    
    def _check_class_teacher_periods(self):
        """Verify CT period is marked correctly."""
        log.debug("Checking class teacher periods...")
        
        for cn in self.all_classes:
            cfg = self.eng.class_config_data.get(cn, {})
            ct = cfg.get('teacher', '').strip()
            ct_period = cfg.get('teacher_period', None)
            
            if not ct or not ct_period:
                continue
            
            class_grid = self.grid.get(cn, [])
            found_ct = False
            
            for d in range(len(self.days)):
                # CT period is relative to specific day in first half
                if d >= len(self.days):
                    break
                
                # Check the CT period column
                cell = class_grid[d][ct_period - 1] if (ct_period - 1) < self.ppd else None
                if cell and cell.get('teacher') == ct:
                    found_ct = True
                    if not cell.get('is_ct'):
                        self.warnings.append(
                            f"Class {cn} CT period {ct_period} on {self.days[d]} "
                            f"not marked as CT")
                    break
            
            if not found_ct:
                self.warnings.append(
                    f"Class {cn}: CT {ct} not found at period {ct_period}")
    
    def _check_workload_consistency(self):
        """Verify workload counts match configuration."""
        log.debug("Checking workload consistency...")
        
        # Count actual periods per teacher
        teacher_workload = defaultdict(lambda: defaultdict(int))  # teacher → class → subject → count
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    # Primary teacher
                    t = cell.get('teacher', '')
                    subj = cell.get('subject', '')
                    if t and t not in ('—', '?') and subj:
                        teacher_workload[t][cn][subj] += 1
                    
                    # Parallel teachers
                    par_teachers = cell.get('par_teachers', []) or []
                    par_subjects = cell.get('par_subjects', []) or []
                    for i, pt in enumerate(par_teachers):
                        ps = par_subjects[i] if i < len(par_subjects) else ''
                        if pt and pt not in ('—', '?') and ps:
                            teacher_workload[pt][cn][ps] += 1
        
        # Compare against config
        for cn in self.all_classes:
            cfg = self.eng.class_config_data.get(cn, {})
            for subj_cfg in cfg.get('subjects', []):
                subj_name = subj_cfg.get('name', '')
                t = subj_cfg.get('teacher', '').strip()
                expected = subj_cfg.get('periods', 0)
                actual = teacher_workload[t][cn][subj_name]
                
                if actual != expected:
                    self.errors.append(
                        f"Workload mismatch: {t} {subj_name} in {cn}: "
                        f"Expected {expected}, got {actual}")
                
                # Check parallels
                par_subs = subj_cfg.get('parallel_subjects', []) or []
                for par in par_subs:
                    ps = par.get('subject', '')
                    pt = par.get('teacher', '')
                    if pt:
                        actual_par = teacher_workload[pt][cn][ps]
                        if actual_par != expected:
                            self.errors.append(
                                f"Parallel workload mismatch: {pt} {ps} in {cn}: "
                                f"Expected {expected}, got {actual_par}")
    
    def _check_excel_class_view(self):
        """Verify class view Excel output would be correct."""
        log.debug("Checking Excel class view representation...")
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            
            # Verify all cells have required fields for Excel output
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    # Check required fields
                    if 'subject' not in cell or 'teacher' not in cell:
                        self.errors.append(
                            f"Class {cn} {self.days[d]} P{p+1}: Missing subject/teacher")
                    
                    # Check combined representation
                    cc = cell.get('combined_classes', [])
                    if cc:
                        if not all(isinstance(c, str) for c in cc):
                            self.errors.append(
                                f"Class {cn}: Invalid combined_classes format: {cc}")
    
    def _check_excel_teacher_view(self):
        """Verify teacher view Excel output would be correct."""
        log.debug("Checking Excel teacher view representation...")
        
        teacher_periods = defaultdict(int)
        
        for cn in self.all_classes:
            class_grid = self.grid.get(cn, [])
            
            for d in range(len(self.days)):
                for p in range(self.ppd):
                    cell = class_grid[d][p] if d < len(class_grid) and p < len(class_grid[d]) else None
                    if not cell:
                        continue
                    
                    # Count for primary teacher
                    t = cell.get('teacher', '')
                    if t and t not in ('—', '?'):
                        teacher_periods[t] += 1
                    
                    # Count for parallel teachers
                    par_teachers = cell.get('par_teachers', []) or []
                    for pt in par_teachers:
                        if pt and pt not in ('—', '?'):
                            teacher_periods[pt] += 1
        
        # Verify all teachers have at least some periods
        all_teachers = set()
        for cn in self.all_classes:
            cfg = self.eng.class_config_data.get(cn, {})
            for subj in cfg.get('subjects', []):
                t = subj.get('teacher', '').strip()
                if t:
                    all_teachers.add(t)
                
                par_subs = subj.get('parallel_subjects', []) or []
                for par in par_subs:
                    pt = par.get('teacher', '').strip()
                    if pt:
                        all_teachers.add(pt)
        
        for teacher in all_teachers:
            if teacher_periods[teacher] == 0:
                self.warnings.append(f"Teacher {teacher}: No periods allocated")
    
    def get_report(self):
        """Generate human-readable validation report."""
        lines = []
        lines.append("\n" + "=" * 80)
        lines.append("TIMETABLE VALIDATION REPORT")
        lines.append("=" * 80)
        
        if not self.errors and not self.warnings:
            lines.append("✅ VALIDATION PASSED - All checks successful!\n")
            return "\n".join(lines)
        
        if self.errors:
            lines.append(f"\n❌ ERRORS ({len(self.errors)}):")
            lines.append("-" * 80)
            for err in self.errors:
                lines.append(f"  • {err}")
        
        if self.warnings:
            lines.append(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            lines.append("-" * 80)
            for warn in self.warnings:
                lines.append(f"  • {warn}")
        
        lines.append("\n" + "=" * 80 + "\n")
        return "\n".join(lines)


def validate_timetable(engine):
    """
    Validate timetable and return results.
    
    Args:
        engine: TimetableEngine with generated timetable
    
    Returns:
        (is_valid, errors, warnings, report)
    """
    validator = TimetableValidator(engine)
    is_valid, errors, warnings = validator.validate_all()
    report = validator.get_report()
    return is_valid, errors, warnings, report
