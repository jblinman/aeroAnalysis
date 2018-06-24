from aeroTesting import AeroRepeatability
golden_probe_path = input('Path to golden probe data: ')
uut_probe_path = input('Path to uut probe data: ')
AeroRepeatability(golden_probe_path, uut_probe_path)