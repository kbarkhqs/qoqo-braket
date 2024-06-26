# Copyright © 2023 HQS Quantum Simulations GmbH.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations under
# the License.
"""Test running local operation with qasm backend."""
from qoqo_for_braket import BraketBackend
from qoqo import Circuit, QuantumProgram
from qoqo.measurements import ClassicalRegister, PauliZProductInput, PauliZProduct  # type:ignore
from qoqo import operations as ops
from typing import List, Any, Optional
import pytest
import sys
import numpy.testing as npt
import numpy as np

list_of_operations = [
    [ops.PauliX(1), ops.PauliX(0), ops.PauliZ(2), ops.PauliX(3), ops.PauliY(4)],
    [
        ops.Hadamard(0),
        ops.CNOT(0, 1),
        ops.CNOT(1, 2),
        ops.CNOT(2, 3),
        ops.CNOT(3, 4),
    ],
    [ops.RotateX(0, 0.23), ops.RotateY(1, 0.12), ops.RotateZ(2, 0.34)],
]


@pytest.mark.parametrize("device", [None, "braket_sv"])
def test_all_no_device(device: Optional[str]) -> None:
    """Test running simple program."""
    circuit = Circuit()
    circuit += ops.PauliX(0)
    circuit += ops.PauliX(2)
    circuit += ops.PauliX(2)
    circuit += ops.ControlledPauliZ(0, 1)
    circuit += ops.MeasureQubit(0, "ro", 0)
    circuit += ops.MeasureQubit(1, "ro", 1)
    circuit += ops.MeasureQubit(2, "ro", 2)
    circuit += ops.PragmaSetNumberOfMeasurements(2, "ro")

    backend = BraketBackend(device)
    (bit_res, _, _) = backend.run_circuit(circuit)
    assert "ro" in bit_res.keys()
    registers = bit_res["ro"]

    assert len(registers) == 2
    assert len(registers[0]) == 3

    for reg in registers:
        npt.assert_array_equal(reg, [True, False, False])


@pytest.mark.parametrize("operations", list_of_operations)
def test_measurement_register_classicalregister(operations: List[Any]):
    backend = BraketBackend()

    circuit = Circuit()
    involved_qubits = set()
    for op in operations:
        involved_qubits.update(op.involved_qubits())
        circuit += op

    circuit += ops.PragmaRepeatedMeasurement("ri", 10)

    measurement = ClassicalRegister(constant_circuit=None, circuits=[circuit])

    try:
        output = backend.run_measurement_registers(measurement=measurement)
    except Exception:
        assert False

    assert len(output[0]["ri"][0]) == len(involved_qubits)
    assert not output[1]
    assert not output[2]


def test_measurement_overwrite():
    backend = BraketBackend()

    circuit_1 = Circuit()
    circuit_1 += ops.DefinitionBit("same", 1, True)
    circuit_1 += ops.PauliX(0)
    circuit_1 += ops.MeasureQubit(0, "same", 0)
    circuit_1 += ops.PragmaSetNumberOfMeasurements(2, "same")

    circuit_2 = Circuit()
    circuit_2 += ops.DefinitionBit("same", 1, True)
    circuit_2 += ops.PauliX(0)
    circuit_2 += ops.PauliX(0)
    circuit_2 += ops.MeasureQubit(0, "same", 0)
    circuit_2 += ops.PragmaSetNumberOfMeasurements(2, "same")

    measurement = ClassicalRegister(constant_circuit=None, circuits=[circuit_1, circuit_2])

    try:
        output = backend.run_measurement_registers(measurement=measurement)
    except Exception:
        assert False

    # output should look like ({'same': [[True], [True], [False], [False]]}, {}, {})
    assert len(output[0]["same"]) == 4
    assert output[0]["same"][0][0]
    assert output[0]["same"][1][0]
    assert not output[0]["same"][2][0]
    assert not output[0]["same"][3][0]
    assert not output[1]
    assert not output[2]


@pytest.mark.parametrize("operations", list_of_operations)
def test_measurement(operations: List[Any]):
    backend = BraketBackend()

    circuit = Circuit()
    involved_qubits = set()
    for op in operations:
        involved_qubits.update(op.involved_qubits())
        circuit += op

    circuit += ops.PragmaRepeatedMeasurement("ri", 10)

    measurement_input = PauliZProductInput(
        number_qubits=len(involved_qubits), use_flipped_measurement=True
    )

    measurement = PauliZProduct(constant_circuit=None, circuits=[circuit], input=measurement_input)

    try:
        _ = backend.run_measurement(measurement=measurement)
    except Exception:
        assert False


def test_batch_measurement():
    input_z = PauliZProductInput(number_qubits=3, use_flipped_measurement=False)

    circuit_1 = Circuit()
    circuit_1 += ops.DefinitionBit("ro_1", 1, False)
    circuit_1 += ops.PauliX(0)
    circuit_1 += ops.MeasureQubit(0, "ro_1", 0)

    input_z.add_pauliz_product("ro_1", [0])
    input_z.add_linear_exp_val("0Z_1", {0: 1.0})

    circuit_2 = Circuit()
    circuit_2 += ops.DefinitionBit("ro_2", 1, False)
    circuit_2 += ops.RotateZ(0, np.pi)
    circuit_2 += ops.MeasureQubit(0, "ro_2", 0)

    input_z.add_pauliz_product("ro_2", [0])
    input_z.add_linear_exp_val("0Z_2", {0: 1.0})

    measurement = PauliZProduct(
        constant_circuit=None, circuits=[circuit_1, circuit_2], input=input_z
    )

    backend = BraketBackend(
        # device="arn:aws:braket:::device/quantum-simulator/amazon/sv1",
        batch_mode=True,
    )
    result = backend.run_measurement(measurement=measurement)

    assert "0Z_1" in result.keys()
    assert result["0Z_1"] == -1.0

    assert "0Z_2" in result.keys()
    assert result["0Z_2"] == -1.0


def test_quantum_program():
    backend = BraketBackend()

    init_circuit = Circuit()
    init_circuit += ops.RotateX(0, "angle_0")
    init_circuit += ops.RotateY(0, "angle_1")

    z_circuit = Circuit()
    z_circuit += ops.DefinitionBit("ro_z", 1, is_output=True)
    z_circuit += ops.PragmaRepeatedMeasurement("ro_z", 1000, None)

    x_circuit = Circuit()
    x_circuit += ops.DefinitionBit("ro_x", 1, is_output=True)
    x_circuit += ops.Hadamard(0)
    x_circuit += ops.PragmaRepeatedMeasurement("ro_x", 1000, None)

    measurement_input = PauliZProductInput(1, False)
    z_basis_index = measurement_input.add_pauliz_product(
        "ro_z",
        [
            0,
        ],
    )
    x_basis_index = measurement_input.add_pauliz_product(
        "ro_x",
        [
            0,
        ],
    )
    measurement_input.add_linear_exp_val(
        "<H>",
        {x_basis_index: 0.1, z_basis_index: 0.2},
    )

    measurement = PauliZProduct(
        constant_circuit=init_circuit,
        circuits=[z_circuit, x_circuit],
        input=measurement_input,
    )

    program = QuantumProgram(
        measurement=measurement,
        input_parameter_names=["angle_0", "angle_1"],
    )

    res = backend.run_program(
        program=program, params_values=[[0.785, 0.238], [0.234, 0.653], [0.875, 0.612]]
    )

    assert len(res) == 3
    for el in res:
        assert float(el["<H>"])

    measurement = ClassicalRegister(constant_circuit=None, circuits=[init_circuit, init_circuit])

    program = QuantumProgram(measurement=measurement, input_parameter_names=["angle_0", "angle_1"])

    res = backend.run_program(
        program=program, params_values=[[0.785, 0.238], [0.234, 0.653], [0.875, 0.612]]
    )

    assert len(res) == 3
    assert res[0][0]
    assert not res[0][1]
    assert not res[0][2]


if __name__ == "__main__":
    pytest.main(sys.argv)
