import hashlib
import random


def get_worker_emoji(text):
    """
    Returns a Unicode animal emoji based on the hash value of the input string.

    Args:
        text (str): The string to hash.

    Returns:
        str: An animal emoji selected based on the hash value.
    """
    # Define a list of animal emojis (and some food, plant, and other emojis for variety)
    # Unicode 6.0 (2010) added many animal emojis, but they are spread across several blocks.
    # Here is a representative list.
    animal_emojis = [
        '🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯',
        '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐥', '🦆',
        '🦅', '🦉', '🐴', '🦄', '🐝', '🐛', '🦋', '🐌', '🐞', '🐜',
        '🦟', '🦗', '🕷️', '🕸️', '🦂', '🐢', '🐍', '🦎', '🦖', '🦕',
        '🐙', '🦑', '🦐', '🦀', '🐠', '🐟', '🐡', '🐬', '🦈', '🐳',
        '🐋', '🐊', '🐅', '🐆', '🦓', '🦍', '🦧', '🦣', '🐘', '🦛',
        '🦏', '🐪', '🐫', '🦒', '🦘', '🦥', '🦦', '🦨', '🦡', '🐾',
        # Food
        '🍎', '🍊', '🍓', '🍒', '🍑', '🍍', '🍇', '🍉', '🍌', '🍋',
        '🥑', '🌽', '🥕', '🥔', '🍠', '🍙', '🍣', '🍜', '🍩', '🍦',
        '🍫', '🎂', '🍭', '🍮', '☕', '🍵', '🥂', '🍻', '🥛', '🥤',
        # Plants & Nature
        '🌸', '🌻', '🌹', '🌷', '🍀', '🌲', '🌳', '🌴', '🌵', '🌱',
        '🌿', '🌾', '🍂', '🍁', '🍄', '🌍', '🌎', '🌏', '🌕', '🌟',
        '🌈', '✨',
        # Weather & Events
        '☀️', '🌤️', '⛅', '🌥️', '🌦️', '🌧️', '🌨️', '🌩️', '🌪️', '🌬️',
        '🌈', '☔', '💧', '🌊', '💨', '🔥', '🎉', '🎊', '🎀', '🎁',
        '🎈', '🎁', '🎂', '💎', '👑',
        # Other
        '❤️', '🧡', '💛', '💚', '💙', '💜', '🤎', '🖤', '🤍', '🧡',
        '💡', '💎', '🔑', '🎵', '🎶', '💯', '✅', '✔️', '💖', '💓',
        '💗', '💕', '💞', '💘', '🧡', '💛', '💚', '💙', '💜', '🤎',
        '🤍', '💫', '🌟', '✨', '🌈', '💖', '🥳'
    ]

    # Encode the string to bytes and calculate its hash value
    hash_object = hashlib.sha256(text.encode())
    hash_digest = hash_object.hexdigest()

    # Convert the hash value to an integer and use it as an index for the emoji list
    index = int(hash_digest, 16) % len(animal_emojis)

    return animal_emojis[index]


if __name__ == '__main__':
    # Example usage
    input_string1 = "I love animals!"
    input_string2 = "A happy cat."
    input_string3 = "The jungle."

    print(f"'{input_string1}' emoji: {get_worker_emoji(input_string1)}")
    print(f"'{input_string1}' emoji: {get_worker_emoji(input_string1)}")
    print(f"'{input_string1}' emoji: {get_worker_emoji(input_string1)}")
    print(f"'{input_string2}' emoji: {get_worker_emoji(input_string2)}")
    print(f"'{input_string3}' emoji: {get_worker_emoji(input_string3)}")
    print(f"'{input_string3}' emoji: {get_worker_emoji(input_string3)}")
    print(f"'{input_string3}' emoji: {get_worker_emoji(input_string3)}")
