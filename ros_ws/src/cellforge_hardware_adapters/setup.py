from setuptools import find_packages, setup

package_name = "cellforge_hardware_adapters"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/hardware_cell.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Production hardware device adapters and vendor interfaces for CellForge.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "hardware_device_node = cellforge_hardware_adapters.ros_node:main",
            "hardware_safety_status_node = cellforge_hardware_adapters.ros_node:safety_main",
        ],
    },
)
