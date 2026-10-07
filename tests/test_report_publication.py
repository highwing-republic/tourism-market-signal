"""The scheduled publisher must commit every tracked report output before rebasing."""
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_generated_statistics_do_not_block_publication(tmp_path):
    def git(*args):
        return subprocess.check_output(
            ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args],
            cwd=tmp_path, text=True,
        ).strip()

    git('init', '-q')
    (tmp_path / '.gitignore').write_text((ROOT / '.gitignore').read_text(), encoding='utf-8')
    outputs = ['docs/index.html', 'data/latest.json', 'data/history/2026-10-07.json',
               'data/public_statistics/latest.json']
    for name in outputs:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('previous\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'Initial report')
    for name in outputs:
        (tmp_path / name).write_text('updated\n', encoding='utf-8')
    (tmp_path / '.env').write_text('PRIVATE_TEST_VALUE=not-a-secret\n', encoding='utf-8')
    (tmp_path / 'data/logs').mkdir()
    (tmp_path / 'data/logs/run.log').write_text('local runtime log\n', encoding='utf-8')

    workflow = (ROOT / '.github/workflows/daily-report.yml').read_text(encoding='utf-8')
    stage_line = next(line.strip() for line in workflow.splitlines()
                      if line.strip().startswith('git add '))
    git(*shlex.split(stage_line)[1:])
    assert set(git('diff', '--cached', '--name-only').splitlines()) == set(outputs)
    git('commit', '-qm', 'Updated report')
    # git pull --rebase rejects this exact unstaged-diff condition.
    assert git('status', '--porcelain') == ''
