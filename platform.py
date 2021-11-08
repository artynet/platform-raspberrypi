# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import copy
import platform

from platformio.managers.platform import PlatformBase


class RaspberrypiPlatform(PlatformBase):

    def is_embedded(self):
        return True

    def configure_default_packages(self, variables, targets):
        # configure arduino core package.
        # select the right one based on the build.core, disable other one.
        board = variables.get("board")
        board_config = self.board_config(board)
        build_core = variables.get(
            "board_build.core", board_config.get("build.core", "arduino"))

        frameworks = variables.get("pioframework", [])
        if "arduino" in frameworks:
            if build_core == "arduino":
                self.frameworks["arduino"]["package"] = "framework-arduino-mbed"
                self.packages["framework-arduinopico"]["optional"] = True
                self.packages["toolchain-pico"]["optional"] = True 
                self.packages.pop("toolchain-pico", None)
            elif build_core == "earlephilhower":
                self.frameworks["arduino"]["package"] = "framework-arduinopico"
                self.packages["framework-arduino-mbed"]["optional"] = True
                self.packages.pop("toolchain-gccarmnoneeabi", None)
                self.packages["toolchain-pico"]["optional"] = False                
            else:
                sys.stderr.write(
                    "Error! Unknown build.core value '%s'. Don't know which Arduino core package to use." % build_core)

        # if we want to build a filesystem, we need the tools.
        if "buildfs" in targets:
            self.packages['tool-mklittlefs']['optional'] = False

        # configure J-LINK tool
        jlink_conds = [
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if variables.get("board"):
            board_config = self.board_config(variables.get("board"))
            jlink_conds.extend([
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            ])
        jlink_pkgname = "tool-jlink"
        if not any(jlink_conds) and jlink_pkgname in self.packages:
            del self.packages[jlink_pkgname]

        return PlatformBase.configure_default_packages(self, variables, targets)

    def get_boards(self, id_=None):
        result = PlatformBase.get_boards(self, id_)
        if not result:
            return result
        if id_:
            return self._add_default_debug_tools(result)
        else:
            for key, value in result.items():
                result[key] = self._add_default_debug_tools(result[key])
        return result

    def _add_default_debug_tools(self, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        for link in ("cmsis-dap", "jlink", "raspberrypi-swd", "picoprobe"):
            if link not in upload_protocols or link in debug["tools"]:
                continue

            if link == "jlink":
                assert debug.get("jlink_device"), (
                    "Missed J-Link Device ID for %s" % board.id)
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if", "SWD",
                            "-select", "USB",
                            "-device", debug.get("jlink_device"),
                            "-port", "2331"
                        ],
                        "executable": ("JLinkGDBServerCL.exe"
                                       if platform.system() == "Windows" else
                                       "JLinkGDBServer")
                    },
                    "onboard": link in debug.get("onboard_tools", [])
                }
            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, ("Missing target configuration for %s" %
                                        board.id)
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-raspberrypi",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "interface/%s.cfg" % link,
                            "-f", "target/%s" % openocd_target
                        ]
                    }
                }

        board.manifest["debug"] = debug
        return board

    def configure_debug_options(self, initial_debug_options, ide_data):
        debug_options = copy.deepcopy(initial_debug_options)
        adapter_speed = initial_debug_options.get("speed", "5000")
        if adapter_speed:
            server_options = debug_options.get("server") or {}
            server_executable = server_options.get("executable", "").lower()
            if "target/cmsis-dap.cfg" in server_options.get("arguments", []):
                debug_options["server"]["arguments"].extend(
                    ["-c", "adapter_khz %s" % adapter_speed]
                )
            elif "jlink" in server_executable:
                debug_options["server"]["arguments"].extend(
                    ["-speed", adapter_speed]
                )

        return debug_options
