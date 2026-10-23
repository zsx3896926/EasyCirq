"""One-off: print the net_flag branch of reconcile and the verify function."""
import importlib.util
import inspect

spec = importlib.util.spec_from_file_location('eda_exec', 'design-hardware/scripts/eda_exec.py')
eda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eda)
src = inspect.getsource(eda.reconcile)
i = src.find("elif op['op'] == 'net_flag'")
print(src[i:i + 2600])
print('=====VERIFY=====')
vsrc = inspect.getsource(eda.verify_against_snapshot)
print(vsrc[:3000])
