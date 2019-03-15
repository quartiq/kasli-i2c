import telnetlib

class FS(telnetlib.Telnet):
    prompts = [b"[>|#] "]

    def __init__(self, host, password):
        super().__init__(host, 23, 10)
        self.read_until(b"Username: ")
        self.write(b"admin\r")
        self.read_until(b"Password: ")
        self.write("{}\r".format(password).encode())
        self.expect(self.prompts)
        self.cmd("terminal length 0")
        self.cmd("enable 15")

    def cmd(self, cmd):
        cmd = "{}\r".format(cmd).encode()
        self.write(cmd)
        index, match, out = self.expect(self.prompts)
        return out

    def poe(self, port, enable=True):
        self.cmd("configure terminal")
        self.cmd("interface GigabitEthernet 1/{}".format(port))
        self.cmd("poe mode plus" if enable else "no poe mode")
        self.cmd("exit")
        self.cmd("exit")

if __name__ == "__main__":
    import sys
    import time
    n = FS(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 4:
        n.poe(sys.argv[3], bool(sys.argv[4]))
    else:
        n.poe(sys.argv[3], False)
        time.sleep(.1)
        n.poe(sys.argv[3], True)
