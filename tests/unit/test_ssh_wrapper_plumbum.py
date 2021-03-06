import io
import os
import socket
import tempfile
import unittest
from textwrap import dedent
from unittest.mock import Mock
from unittest.mock import patch

from plumbum.machines.paramiko_machine import ParamikoMachine

from sshkernel.ssh_wrapper_plumbum import SSHWrapperPlumbum
from sshkernel.ssh_wrapper_plumbum import append_footer
from sshkernel.ssh_wrapper_plumbum import load_ssh_config_for_plumbum
from sshkernel.ssh_wrapper_plumbum import merge_stdout_stderr
from sshkernel.ssh_wrapper_plumbum import process_output


class SSHWrapperPlumbumTest(unittest.TestCase):
    def setUp(self):
        def new_test_instance():
            subscriptable = Mock()
            subscriptable.popen = Mock(return_value=subscriptable)
            subscriptable.__getitem__ = Mock(return_value=subscriptable)
            subscriptable.iter_lines = Mock(
                return_value=([("output", None), (None, "err")])
            )

            remote_double = Mock(spec=ParamikoMachine)
            remote_double.__getitem__ = Mock(return_value=subscriptable)

            instance = SSHWrapperPlumbum()
            instance._remote = remote_double

            return instance

        self.instance = new_test_instance()

    def test_connect_should_raise_socket_error(self):
        # FIXME: fix setUp() to pass the line below
        # self.assertIsNone(self.instance._remote)
        self.assertFalse(self.instance.isconnected())

        with self.assertRaises(socket.gaierror):
            self.instance.connect("dummy")

    def test_connect_updates_attributes(self):
        remote_double = Mock()
        self.instance._build_remote = Mock(return_value=remote_double)
        dummy = "dummy"
        # self.assertIsNone(self.instance._remote)
        self.assertFalse(self.instance.isconnected())
        self.assertEqual(self.instance._host, "")

        self.instance.connect(dummy)

        self.assertTrue(self.instance.isconnected())
        self.assertEqual(self.instance._host, dummy)
        remote_double.env.update.assert_called()

    @unittest.skip("fix setUp")
    def test_exec_command_returns_error_at_first(self):
        with self.assertRaises(socket.gaierror):
            self.instance.exec_command("yo", lambda line: None)

    @unittest.skip
    def test_exec_command_returns_stream(self):
        self.instance.connect("myserver")
        print_mock = Mock()

        ret = self.instance.exec_command("yo", print_mock)

    def test_exec_command_return_exit_code(self):
        print_mock = Mock()

        code = self.instance.exec_command("ls", print_mock)

        self.assertIsInstance(code, int)

    def test_close_should_delegate(self):
        mock = Mock()
        self.instance._remote.close = mock
        self.instance.close()

        mock.assert_called_once()

    def test_append_footer(self):
        cmd = """
ls
ls
yo
"""
        marker = "THISISMARKER"

        full_command = append_footer(cmd, marker)

        self.assertIsInstance(full_command, str)
        self.assertEqual(full_command.count(marker), 6)

    @unittest.skip("Fail to patch plumbum")
    @patch(
        "sshkernel.ssh_wrapper_plumbum.SSHWrapperPlumbum.get_cwd", return_value="/tmp"
    )
    @patch(
        "plumbum.machines.paramiko_machine.ParamikoMachine.cwd.getpath._path",
        return_value="/home",
    )
    def test_update_workdir(self, mock1, mock2):
        mock = Mock()  # return_value='/')
        self.instance.get_cwd = mock
        self.instance._remote = mock
        newdir = "/some/where"

        self.instance.update_workdir(newdir)

        mock.assert_called_once()

    @unittest.skip("Fail to patch the instance created in setUp()")
    def test_post_exec(self, env_mock):
        self.instance._remote.env = env_mock
        env_out = """code: 255
env: A=1^@B=2^@TOKEN=AAAA9B==
pwd: /some/where
"""

        code = self.instance.post_exec_command(env_out)
        self.assertEqual(255, code)

    @patch("sshkernel.ssh_wrapper_plumbum.SSHWrapperPlumbum")
    def test__update_interrupt_function(self, proc):
        fn_before = self.instance.interrupt_function
        self.instance._update_interrupt_function(proc)
        fn_after = self.instance.interrupt_function

        self.assertTrue(callable(fn_before))
        self.assertTrue(callable(fn_after))
        self.assertNotEqual(fn_before, fn_after)

    @patch("sshkernel.ssh_wrapper_plumbum.SSHWrapperPlumbum")
    def test__update_interrupt_function_inject_proc_to_closure(self, proc):
        self.instance._update_interrupt_function(proc)
        fn_after = self.instance.interrupt_function

        proc.close.assert_not_called()
        fn_after()
        proc.close.assert_called_once()


class UtilityTest(unittest.TestCase):
    def test_merge_stdout_stderr(self):
        lines = [
            ("a", None),
            ("b\n", None),
            (None, "c"),
            ("d", None),
        ]

        def outs():
            for line in lines:
                yield line

        merged = merge_stdout_stderr(outs())
        lines = list(merged)

        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertIsNotNone(line)

    def test_process_output_with_newline(self):
        marker = "MARKER"

        def gen_iterator():
            lines = io.StringIO(
                """line1
line2
{marker}code: 0{marker}
{marker}pwd: /tmp{marker}
""".format(
                    marker=marker
                )
            )
            for line in lines:
                yield (line, None)

        iterator = gen_iterator()
        print_function = Mock()

        env_info = process_output(iterator, marker, print_function)
        env_info_expected = "code: 0\npwd: /tmp\n"

        self.assertEqual(env_info, env_info_expected)
        print_function.assert_any_call("line1\n")
        print_function.assert_any_call("line2\n")

    def test_process_output_without_newline(self):
        marker = "MARKER"

        def gen_iterator():
            lines = io.StringIO(
                """line1
line2
line3{marker}code: 0{marker}
{marker}pwd: /tmp{marker}
""".format(
                    marker=marker
                )
            )
            for line in lines:
                yield (line, None)

        iterator = gen_iterator()
        print_function = Mock()
        env_info = process_output(iterator, marker, print_function)

        print_function.assert_any_call("line1\n")
        print_function.assert_any_call("line2\n")
        print_function.assert_any_call("line3")  # without newline
        self.assertEqual(env_info, "code: 0\npwd: /tmp\n")

    def test_load_ssh_config_for_plumbum(self):
        skip = "skip_dict_equality_test"
        cases = [
            dict(
                input=dedent(
                    """
                    Host test
                        HostName 127.0.0.10
                        User testuser
                        IdentityFile ~/.ssh/id_rsa_test
                    """
                ),
                expect=(
                    "127.0.0.10",
                    dict(
                        port=None,
                        user="testuser",
                        keyfile=[os.path.expanduser("~/.ssh/id_rsa_test")],
                        load_system_ssh_config=False,
                    ),
                    None,
                ),
            ),
            dict(
                input=dedent(
                    """
                    Host test
                        IdentityFile ~/.ssh/id_rsa_test
                    """
                ),
                expect=("test", skip, None),
            ),
            dict(
                input=dedent(
                    """
                    Host test
                        User admin
                        Port 2222
                        HostName 1.2.3.4
                        IdentityFile ~/.ssh/id_rsa_test

                    Host *
                        ForwardAgent yes
                    """
                ),
                expect=("1.2.3.4", skip, "yes"),
            ),
            dict(
                input=dedent(
                    """
                    Host test
                        User admin
                        Port 2222
                        IdentityFile ~/.ssh/id_rsa_test
                        ProxyCommand ssh -W %h:%p target
                    """
                ),
                expect=(
                    "test",
                    dict(
                        user="admin",
                        port=2222,
                        keyfile=[os.path.expanduser("~/.ssh/id_rsa_test")],
                        load_system_ssh_config=True,
                    ),
                    None,
                ),
            ),
        ]

        case_raises = dedent(
            """
            Host test
                User user
                Hostname bastion
                ProxyCommand ssh -W %h:%p target
            """
        )

        for case in cases:
            input, expect = case["input"], case["expect"]
            (hostname, lookup, forward) = expect
            with tempfile.NamedTemporaryFile("w") as f:
                f.write(input)
                f.seek(0)
                host = "test"
                got = load_ssh_config_for_plumbum(f.name, host)

            self.assertEqual(hostname, got[0])
            if lookup is not skip:
                # can't assert missin_host_policy equality
                lookup["missing_host_policy"] = got[1].get("missing_host_policy")
                self.assertDictEqual(lookup, got[1])

            self.assertEqual(forward, got[2])

        with tempfile.NamedTemporaryFile("w") as f:
            f.write(case_raises)
            f.seek(0)
            host = "test"
            with self.assertRaises(ValueError):
                _ = load_ssh_config_for_plumbum(f.name, host)
