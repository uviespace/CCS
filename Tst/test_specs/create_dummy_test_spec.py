import data_model
tspec = data_model.TestSpecification()
tspec.add_sequence()
tspec.add_sequence()
tseq = tspec.get_sequence(sequence_number=0)
tseq.add_step_below()
tseq.add_step_below(1)
tseq.add_step_below(2)
tseq.add_step_below(3)
tseq = tspec.get_sequence(sequence_number=1)
tseq.add_step_below()
tseq.add_step_below(1)
tseq.add_step_below(2)
tseq.add_step_below(3)

data = tspec.encode_to_json()

with open('test_spec.json', 'w') as file:
    file.write(data)
