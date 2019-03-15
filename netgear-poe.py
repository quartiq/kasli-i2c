import telnetlib

class Netgear(telnetlib.Telnet):
    prompts = [b"\\(Broadcom FASTPATH Switching\\) (\\(.*\\))?[>|#]"]

    def __init__(self, host, password):
        super().__init__(host, 60000, 10)
        self.read_until(b"please wait ...")
        self.write(b"admin\n")
        self.read_until(b"Password:")
        self.write("{}\n".format(password).encode())
        self.expect(self.prompts)
        self.cmd("terminal length 0")
        self.enable()

    def enable(self):
        self.write(b"enable\n")
        self.expect([b"Password:"])
        self.write(b"\n")
        self.expect(self.prompts)

    def cmd(self, cmd):
        cmd = "{}\n".format(cmd).encode()
        self.write(cmd)
        index, match, out = self.expect(self.prompts)
        return out

    def poe(self, port, enable=True):
        self.cmd("configure")
        self.cmd("interface {}".format(port))
        self.cmd("poe" if enable else "no poe")
        self.cmd("exit")
        self.cmd("exit")

if __name__ == "__main__":
    import sys
    import time
    n = Netgear(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 4:
        n.poe(sys.argv[3], bool(sys.argv[4]))
    else:
        n.poe(sys.argv[3], False)
        time.sleep(.1)
        n.poe(sys.argv[3], True)
