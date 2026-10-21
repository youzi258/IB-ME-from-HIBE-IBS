"""Generate the complete reduced comparison after its seven missing jobs end."""
import argparse
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-base', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    base, repo = args.batch_base.resolve(), args.repository.resolve()
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo/'src'))
    from experiments.research.ten_combination_basic_comparison import read_verified, combine, write_comparison
    from experiments.research.ten_combination_benchmark import write_json
    from experiments.research.ten_combination_summary import plots
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location('basic_controller_status', Path(__file__).with_name('run_after_calibration.py'))
    process_status = module_from_spec(spec)
    spec.loader.exec_module(process_status)
    batch_id = 'ten-combinations-basic-supplement-20261021-01'
    print(json.dumps(dict(status='waiting', batch_id=batch_id)), flush=True)
    while process_status.calibration_active(batch_id):
        time.sleep(15)
    design = json.loads((base/'basic-design.json').read_bytes())
    sources = {design['reused_batch']: read_verified(base/'calibration-02/public'),
               design['supplemental_batch']: read_verified(base/'basic-supplement-01/public')}
    result = combine(design, sources)
    write_comparison(base/'basic-comparison', result)
    plots(base/'basic-comparison', result)
    status = dict(status=result['status'], completed_cases=result['completed_cases'], planned_cases=10,
                  counts=result['counts'], output=str(base/'basic-comparison'))
    write_json(base/'basic-comparison-status.json', status)
    print(json.dumps(status), flush=True)


if __name__ == '__main__':
    main()
