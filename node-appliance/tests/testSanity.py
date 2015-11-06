#!/usr/bin/env python
# vim: et ts=4 sw=4 sts=4

import logging
from logging import debug

logging.basicConfig(level=logging.DEBUG)

import unittest
import sh
import os
import tempfile
from virt import Image, VM, CloudConfig

NODE_IMG = os.environ.get("TEST_NODE_ROOTFS_IMG",
                          "ovirt-node-appliance.qcow2")


def gen_ssh_identity_file():
    f = tempfile.mkdtemp("testing-ssh") + "/id_rsa"
    sh.ssh_keygen(b=2048, t="rsa", f=f, N="", q=True)
    return f


class MachineTestCase(unittest.TestCase):
    @staticmethod
    def _start_vm(name, srcimg, tmpimg, magicnumber):
        debug("Strating new VM %s" % name)

        ssh_port = 22000 + int(magicnumber)
        ipaddr = "10.11.12.%s" % magicnumber

        img = Image(srcimg).reflink(tmpimg)
        dom = VM.create(name, img, ssh_port=ssh_port)
        dom._ssh_identity_file = gen_ssh_identity_file()

        cc = CloudConfig()
        cc.instanceid = name + "-ci"
        cc.password = str(magicnumber)
        # cc.runcmd = "ip link set dev eth1 up ; ip addr add {ipaddr}/24 dev eth1".format(ipaddr=ipaddr)
        cc.runcmd = "nmcli con add con-name bus0 ifname eth1 autoconnect yes type ethernet ip4 {ipaddr}/24 ; nmcli con up id bus0".format(ipaddr=ipaddr)
        with open(dom._ssh_identity_file + ".pub", "rt") as src:
            cc.ssh_authorized_keys = [src.read().strip()]
        dom.set_cloud_config(cc)

        return dom


class NodeTestCase(MachineTestCase):
    @classmethod
    def setUpClass(cls):
        debug("SetUpClass %s" % cls)
        n = "%s-node" % cls.__name__
        cls.node = cls._start_vm(n, NODE_IMG, n + ".qcow2", 77)

    @classmethod
    def tearDownClass(cls):
        debug("Tearing down %s" % cls)
        cls.node.undefine()

    def setUp(self):
        debug("Setting up %s" % self)
        self.snapshot = self.node.snapshot()
        self.node.start()

    def tearDown(self):
        debug("Tearing down %s" % self)
        self.snapshot.revert()


class TestNodeTestcase(NodeTestCase):
    """Let's ensure that the basic functionality is working
    """
    def test_snapshots_work(self):
        has_kernel = lambda: "kernel" in self.node.ssh("rpm -q kernel")

        self.assertTrue(has_kernel())

        with self.node.snapshot().context():
            self.node.ssh("rpm -e --nodeps kernel")
            with self.assertRaises(sh.ErrorReturnCode_1):
                has_kernel()

        self.assertTrue(has_kernel())

    def test_ssh_works(self):
        self.node.ssh("pwd")

    def test_reboot_works(self):
        with self.assertRaises(sh.ErrorReturnCode_255):
            self.node.ssh("reboot")
        self.node.wait_reboot(timeout=60)
        self.node.ssh("pwd")


class TestBasicNode(NodeTestCase):
    def test_required_packages(self):
        pkgs = ["kernel", "vdsm"]
        self.node.ssh("rpm -q " + " ".join(pkgs))


@unittest.skip("We need to test the installed image to fix this, blocked by https://bugzilla.redhat.com/1278878")
class TestImgbaseNode(NodeTestCase):
    def test_installed(self):
        debug("%s" % self.node.ssh("imgbase --version"))

    def test_has_vgs(self):
        vgs = self.node.ssh("vgs --noheadings").strip().splitlines()
        debug("VGs: %s" % vgs)
        self.assertGreater(len(vgs), 0, "No VGs found")

    def test_has_layout(self):
        self.node.ssh("imgbase layout")


class IntegrationTestCase(MachineTestCase):
    ENGINE_ANSWERS = """
# For 3.6
[environment:default]
OVESETUP_CONFIG/adminPassword=str:PASSWORD
OVESETUP_CONFIG/fqdn=str:engine.example.com
OVESETUP_ENGINE_CONFIG/fqdn=str:engine.example.com
OVESETUP_VMCONSOLE_PROXY_CONFIG/vmconsoleProxyHost=str:engine.example.com

OVESETUP_DIALOG/confirmSettings=bool:True
OVESETUP_CONFIG/applicationMode=str:both
OVESETUP_CONFIG/remoteEngineSetupStyle=none:None
OVESETUP_CONFIG/storageIsLocal=bool:False
OVESETUP_CONFIG/firewallManager=str:firewalld
OVESETUP_CONFIG/remoteEngineHostRootPassword=none:None
OVESETUP_CONFIG/firewallChangesReview=bool:False
OVESETUP_CONFIG/updateFirewall=bool:True
OVESETUP_CONFIG/remoteEngineHostSshPort=none:None
OVESETUP_CONFIG/storageType=none:None
OSETUP_RPMDISTRO/requireRollback=none:None
OSETUP_RPMDISTRO/enableUpgrade=none:None
OVESETUP_DB/database=str:engine
OVESETUP_DB/fixDbViolations=none:None
OVESETUP_DB/secured=bool:False
OVESETUP_DB/host=str:localhost
OVESETUP_DB/user=str:engine
OVESETUP_DB/securedHostValidation=bool:False
OVESETUP_DB/port=int:5432
OVESETUP_ENGINE_CORE/enable=bool:True
OVESETUP_CORE/engineStop=none:None
OVESETUP_SYSTEM/memCheckEnabled=bool:False
OVESETUP_SYSTEM/nfsConfigEnabled=bool:False
OVESETUP_CONFIG/sanWipeAfterDelete=bool:True
OVESETUP_PKI/organization=str:Test
OVESETUP_CONFIG/engineHeapMax=str:3987M
OVESETUP_CONFIG/isoDomainName=str:ISO_DOMAIN
OVESETUP_CONFIG/isoDomainMountPoint=str:/var/lib/exports/iso
OVESETUP_CONFIG/isoDomainACL=str:*(rw)
OVESETUP_CONFIG/engineHeapMin=str:100M
OVESETUP_AIO/configure=none:None
OVESETUP_AIO/storageDomainName=none:None
OVESETUP_AIO/storageDomainDir=none:None
OVESETUP_PROVISIONING/postgresProvisioningEnabled=bool:True
OVESETUP_APACHE/configureRootRedirection=bool:True
OVESETUP_APACHE/configureSsl=bool:True
OVESETUP_CONFIG/websocketProxyConfig=bool:True
OVESETUP_RHEVM_SUPPORT/configureRedhatSupportPlugin=bool:False
OVESETUP_VMCONSOLE_PROXY_CONFIG/vmconsoleProxyConfig=bool:True
OVESETUP_VMCONSOLE_PROXY_CONFIG/vmconsoleProxyPort=int:2222
"""

    @classmethod
    def setUpClass(cls):
        print("SetUpClass %s" % cls)
        n = "%s-" % cls.__name__
        cls.node = cls._start_vm(n + "node", NODE_IMG,
                                 n + "node.qcow2", 77)
        ENGINE_IMG = "ovirt-engine-appliance.qcow2"
        cls.engine = cls._start_vm(n + "engine", ENGINE_IMG,
                                   n + "engine.qcow2", 88)

        #
        # Do the engine setup
        # This assumes that the engine was tested already and
        # this could probably be pulled in a separate testcase
        #
        cls._engine_setup()

    @classmethod
    def _engine_setup(cls):
        debug("Installing engine")
        cls.engine.post("/root/ovirt-engine-answers",
                        cls.ENGINE_ANSWERS)
#        cls.engine.post("/etc/ovirt-engine/engine.conf.d/90-mem.conf",
#                        "ENGINE_PERM_MIN=128m\nENGINE_HEAP_MIN=1g\n")  # To reduce engines mem requirements
        cls.engine.post("/root/.ovirtshellrc", """
[ovirt-shell]
username = admin@internal
password = PASSWORD

renew_session = False
timeout = None
extended_prompt = False
url = https://127.0.0.1/ovirt-engine/api
insecure = True
kerberos = False
filter = False
session_timeout = None
ca_file = None
dont_validate_cert_chain = True
key_file = None
cert_file = None
""")

        cls.engine.start()
        cls.engine.ssh("sed -i '/^127.0.0.1/ s/$/ engine.example.com/' /etc/hosts")
        cls.engine.ssh("engine-setup --offline --config-append=/root/ovirt-engine-answers")
        cls.engine.shutdown()
        cls.engine.wait_event("lifecycle")
        debug("Installation completed")

    @classmethod
    def tearDownClass(cls):
        debug("Tearing down %s" % cls)
        cls.node = None
        cls.engine = None

    def setUp(self):
        self.node_snapshot = self.node.snapshot()
        self.engine_snapshot = self.engine.snapshot()
        self.node.start()
        self.engine.start()

    def tearDown(self):
        self.node_snapshot.revert()
        self.engine_snapshot.revert()


class TestIntegrationTestCase(IntegrationTestCase):
    def test_intra_network_connectivity(self):
        self.node.ssh("ifconfig")
        self.engine.ssh("ifconfig")

        self.node.ssh("arp -n")
        self.engine.ssh("arp -n")

        self.node.ssh("ping -c1 10.11.12.88")
        self.engine.ssh("ping -c1 10.11.12.77")

    def test_engine_is_up(self):
        self.engine.ssh("curl --fail 127.0.0.1 | grep -i engine")

    def test_node_can_reach_engine(self):
        self.node.ssh("ping -c1 10.11.12.88")
        self.engine.ssh("ping -c1 10.11.12.77")
        self.node.ssh("curl --fail 10.11.12.88 | grep -i engine")

    def engine_shell(self, cmd):
        oshell = lambda cmd: self.engine.ssh("ovirt-shell --connect -E %r" % cmd)
        def wait_engine():
            while "disconnected" in oshell("ping"):
                    debug("Waiting for engine ...")
        wait_engine()
        return oshell(cmd)

    def test_add_host(self):
        # Check if the shell is working
        self.engine_shell("ping")

        debug("Add the host")
        self.engine_shell("add host --name foo --address 10.11.12.77 --root_password 77 --cluster-name Default")
        self.assertTrue("foo" in self.engine_shell("list hosts"))

        debug("Check that it will get up")
        # FIXME

    @unittest.skip("Not implemented")
    def test_add_storage(self):
        pass

    @unittest.skip("Not implemented")
    def test_spawn_vm(self):
        self.test_add_host()
        self.test_add_storage()
        pass


if __name__ == "__main__":
    unittest.main()
