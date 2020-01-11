import telnetlib

class FS(telnetlib.Telnet):
    prompts = [b"[>|#]"]

    def __init__(self, host, password):
        super().__init__(host, 23, 10)
        self.read_until(b"Username: ")
        self.write(b"admin\r")
        self.read_until(b"Password: ")
        self.write("{}\r".format(password).encode())
        self.expect(self.prompts)
        self.cmd("enable")
        self.cmd("terminal length 0")

    def cmd(self, cmd):
        cmd = "{}\r".format(cmd).encode()
        self.write(cmd)
        index, match, out = self.expect(self.prompts)
        return out

    def poe(self, port, enable=True):
        self.cmd("config")
        self.cmd("interface GigaEthernet 0/{}".format(port))
        self.cmd("no poe disable" if enable else "poe disable")
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
