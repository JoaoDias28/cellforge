from setuptools import find_packages, setup

package_name = "cellforge_simulation"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (
            f"share/{package_name}/launch",
            ["launch/simulation_bridge.launch.py", "launch/contract_scenario.launch.py"],
        ),
    ],
    install_requires=["setuptools", "PyYAML>=6,<7"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Deterministic Isaac simulation and ROS 2 scenario control bridge.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "simulation_bridge = cellforge_simulation.ros_node:main",
            "isaac_l2_adapter = cellforge_simulation.l2_ros_node:main",
        ]
    },
)
