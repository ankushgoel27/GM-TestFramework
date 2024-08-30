
import argparse
from pathlib import Path
from typing import Any

from classes.commands.BaseCommand import DEFAULT_CONFIG, BaseCommand
from classes.server.TestFrameworkServer import manage_server
from utils import async_utils, file_utils

class RunTestsCommand(BaseCommand):
    def __init__(self, options: argparse.Namespace):
        BaseCommand.__init__(self, options)

    @classmethod
    def register_command(cls, subparsers: argparse._SubParsersAction):
        parser: argparse.ArgumentParser = subparsers.add_parser('runTests', help='Runs the testframework and collects all results')

        parser.add_argument('-yypc', '--yypc-path', type=str, required=True, help='The path to the project compiler')
        parser.add_argument('-yyp', '--project-path', type=str, required=True, help='The path to the project file (.yyp)')
        parser.add_argument('-o', '--output-folder', type=str, required=True, help='The path to the output folder')
        parser.add_argument('-t', '--template-folder', type=str, required=True, help='The mode to be used during compilation')
        parser.add_argument('-tc', '--toolchain-folder', type=str, required=True, help='The path to the GMRT toolchain')
        parser.add_argument('-tt', '--target-triple', choices=['x86_64-pc-windows-msvc'], default='x86_64-pc-windows-msvc', help=f'The target platform to build to')
        parser.add_argument('-ac', '--asset-compiler-path', type=str, required=True, help='The location of the GMRT asset compiler')
        parser.add_argument('-aca', '--asset-compiler-args', type=str, default="", help='The arguments to be pass through to the asset compiler')
        parser.add_argument('-m', '--mode', choices=['build-run', 'build-only'], default='build-run', help='The mode to be used during compilation')
        parser.add_argument('-bt', '--build-type', choices=['Debug', 'Release'], default='Debug', help='The type of build (Debug|Release)')
        parser.add_argument('-sbt', '--script-build-type', choices=['Debug', 'Release'], default='Debug', help='The type of script build (Debug|Release)')
        parser.add_argument('-rn', '--run-name', default='xUnit TestFramework', help='The name to be given to the test run')
        parser.add_argument('-ra', '--run-arguments', type=str, default="", help="Arguments to pass to the run mode of YYPC")

        parser.set_defaults(command_class=cls)

    async def execute(self):
        # Run our server management function (start server, run all tests and publish to server, stop server)
        self.project_write_config()
        await async_utils.run_exe_and_capture(self.get_argument("yypc_path"), [
            self.get_argument("project_path"), 
            '-o', self.get_argument("output_folder"),
            '-t', self.get_argument("template_folder"),
            f'-toolchain={self.get_argument("toolchain_folder")}',
            f'-target-triple={self.get_argument("target_triple")}',
            f'-asset-compiler={self.get_argument("asset_compiler_path")}',
            f'-asset-compiler-args={self.get_argument("asset_compiler_args")}',
            f'-build-type={self.get_argument("build_type")}',
            f'-script-build-type={self.get_argument("script_build_type")}',
            f'-mode={self.get_argument("mode")}',
            f'-run-args={self.get_argument("run_arguments")}',
            '-v'])

    def project_write_config(self):
        yyp_file = self.get_argument("project_path")
        yyp_folder = Path(yyp_file).parent

        config_data = {
            **DEFAULT_CONFIG,
            '$$parameters$$.run_name': self.get_argument("run_name"),
        }

        config_file = yyp_folder / 'datafiles' / 'config.json'
        file_utils.save_data_as_json(config_data, config_file)