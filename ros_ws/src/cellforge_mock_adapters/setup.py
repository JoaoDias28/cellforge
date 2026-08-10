from setuptools import find_packages, setup

package_name = "cellforge_mock_adapters"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/mock_cell.launch.py"]),
        (f"share/{package_name}/config", ["config/mock_cell_scenarios.json"]),
    ],
    install_requires=["setuptools", "PyYAML>=6,<7"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="L0 contract mock adapters for the CellForge reference device families.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mock_device_node = cellforge_mock_adapters.ros_node:main",
            "pen_headless_runner = cellforge_mock_adapters.headless:main",
        ],
    },
)
