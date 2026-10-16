from g1.gsm8k import correct_answer, extract_answer, is_correct


def test_the_correct_answer_is_the_number_after_the_four_hashes():
    assert correct_answer("She sells 16 - 3 - 4 = <<16-3-4=9>>9 eggs.\n#### 18") == "18"
    assert correct_answer("Total is 1,000.\n#### 1,000") == "1000"


def test_from_the_model_text_the_last_number_in_the_box_counts():
    assert extract_answer("So she makes \\boxed{18} dollars.") == "18"
    assert extract_answer("First \\boxed{18}, but correcting: \\boxed{20}") == "20"
    assert extract_answer("The cost is \\boxed{\\$1,250.00}.") == "1250"


def test_without_a_box_the_last_number_of_the_text_counts():
    assert extract_answer("She has 3 apples and buys 5 more, so 8 apples.") == "8"
    assert extract_answer("The result is -4.5") == "-4.5"


def test_without_numbers_there_is_no_answer():
    assert extract_answer("I cannot solve this.") is None
    assert extract_answer("") is None


def test_two_answers_are_equal_if_they_are_equal_as_numbers():
    assert is_correct("18", "18.0")
    assert is_correct("0.5", ".5")
    assert is_correct("-3", "-3")
    assert not is_correct("17", "18")
    assert not is_correct(None, "18")
