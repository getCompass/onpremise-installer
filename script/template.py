#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True

from subprocess import Popen, PIPE

script_dir = os.path.dirname(os.path.realpath(__file__))
dist_name = sys.platform

# match с версии 3.11 - в репозитории Ubuntu 20.04 3.8
if dist_name == "linux":
    bin_name = "./packages/go_template_linux"
elif dist_name == "darwin":
    bin_name = "./packages/go_template_darwin"
else:
    exit(1)

root_path = os.path.abspath(script_dir + "/../")
os.chdir(root_path)

p = Popen([bin_name, '--input-tpl-path', sys.argv[1], '--input-var-paths', sys.argv[2], '--out', sys.argv[3], '--override', sys.argv[4] if len(sys.argv) > 4 else ' '], stdout=PIPE, stderr=PIPE, stdin=PIPE)
p.wait()
err = p.stderr.read()
out = p.stdout.read()
    
if (p.returncode == 0):
    exit(0)
else:
    print(err)
    print(out)
    exit(p.returncode)