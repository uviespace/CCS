"""Integration regression against the supplied raw morning pool."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pool_audit', ROOT / 'investigations/audit_pool.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MorningPoolTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / 'chances_alig_2026113_morning.tmpool').exists(), 'Morning pool not supplied')
    def test_complete_reports_and_exact_sdf_preservation(self):
        frames, count, size = audit.reconstruct(ROOT / 'chances_alig_2026113_morning.tmpool')
        self.assertEqual(len(frames), 30)
        self.assertEqual(size, 60363915)
        for frame in frames:
            self.assertEqual(len(frame['data']), 1966140)
            self.assertEqual(sum(frame['packet_counts']), len(frame['data']))
            self.assertEqual(frame['counters'], list(range(2, 979)))
            self.assertEqual(len(frame['data'][61:]), 1966079)
            header = frame['data'][25:61]
            self.assertEqual(int.from_bytes(header[:4], 'little'), 1966116)
            self.assertEqual(header[4] & 3, 1)
            self.assertEqual(int.from_bytes(header[21:23], 'little') & 0x1fff, 1280)
            self.assertEqual(int.from_bytes(header[23:25], 'little') & 0xfff, 1024)
        for frame, ticks in zip(frames, [1280000, 128000, 1280000, 640000]):
            self.assertEqual(int.from_bytes(frame['data'][40:44], 'little'), ticks)
        for index, directory in [(0, '10ms'), (1, '1ms')]:
            path = next((ROOT / directory).glob('*.sdf'))
            self.assertEqual(frames[index]['data'], path.read_bytes())


if __name__ == '__main__':
    unittest.main()
