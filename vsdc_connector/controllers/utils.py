import string


def cleaned_value(s):
    s = str(s)
    return s.translate({ord(c): None for c in string.whitespace})


def success_response(response):
    if not response:
        return
    return type(response) == dict and response.get("status") == "P"


def get_error_message(response):
    """Receives the client response and returns a verbose message to display to the user"""
    if type(response) != dict:
        return str(response)
    try:
        code = response.get("code", 500)
        description = response.get("description", "")
        status = response.get("status", "E")
        assert status != "P"
        if code == 500:
            prefix = "Internal Server Error: "
        else:
            prefix = "VSDC Error: "

        return prefix + str({"code": code, "description": description})

    except AssertionError:
        return
