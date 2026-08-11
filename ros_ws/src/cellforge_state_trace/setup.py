from setuptools import find_packages, setup

package_name = "cellforge_state_trace"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Cell state aggregation and durable trace event recording for CellForge.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "state_aggregator = cellforge_state_trace.aggregator:main",
            "durable_event_recorder = cellforge_state_trace.recorder:main",
        ],
    },
)
