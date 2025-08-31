import hashlib
import random


def get_worker_emoji(text):
    """
    文字列のハッシュ値に基づいて、Unicodeの動物絵文字を返します。

    Args:
        text (str): ハッシュ値を計算する文字列。

    Returns:
        str: ランダムに選ばれた動物絵文字。
    """
    # Unicodeの動物絵文字の範囲を定義
    # Unicode 6.0 (2010年)で追加された動物絵文字のブロック
    # 実際には、複数のブロックに分散しているため、代表的なものをリストアップします。
    animal_emojis = [
        '🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯',
        '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐥', '🦆',
        '🦅', '🦉', '🐴', '🦄', '🐝', '🐛', '🦋', '🐌', '🐞', '🐜',
        '🦟', '🦗', '🕷️', '🕸️', '🦂', '🐢', '🐍', '🦎', '🦖', '🦕',
        '🐙', '🦑', '🦐', '🦀', '🐠', '🐟', '🐡', '🐬', '🦈', '🐳',
        '🐋', '🐊', '🐅', '🐆', '🦓', '🦍', '🦧', '🦣', '🐘', '🦛',
        '🦏', '🐪', '🐫', '🦒', '🦘', '🦥', '🦦', '🦨', '🦡', '🐾',
        # 食べ物
        '🍎', '🍊', '🍓', '🍒', '🍑', '🍍', '🍇', '🍉', '🍌', '🍋',
        '🥑', '🌽', '🥕', '🥔', '🍠', '🍙', '🍣', '🍜', '🍩', '🍦',
        '🍫', '🎂', '🍭', '🍮', '☕', '🍵', '🥂', '🍻', '🥛', '🥤',
        # 植物・自然
        '🌸', '🌻', '🌹', '🌷', '🍀', '🌲', '🌳', '🌴', '🌵', '🌱',
        '🌿', '🌾', '🍂', '🍁', '🍄', '🌍', '🌎', '🌏', '🌕', '🌟',
        '🌈', '✨',
        # 天気・イベント
        '☀️', '🌤️', '⛅', '🌥️', '🌦️', '🌧️', '🌨️', '🌩️', '🌪️', '🌬️',
        '🌈', '☔', '💧', '🌊', '💨', '🔥', '🎉', '🎊', '🎀', '🎁',
        '🎈', '🎁', '🎂', '💎', '👑',
        # その他
        '❤️', '🧡', '💛', '💚', '💙', '💜', '🤎', '🖤', '🤍', '🧡',
        '💡', '💎', '🔑', '🎵', '🎶', '💯', '✅', '✔️', '💖', '💓',
        '💗', '💕', '💞', '💘', '🧡', '💛', '💚', '💙', '💜', '🤎',
        '🤍', '💫', '🌟', '✨', '🌈', '💖', '🥳'
    ]

    # 文字列をバイト列にエンコードしてからハッシュ値を計算
    hash_object = hashlib.sha256(text.encode())
    hash_digest = hash_object.hexdigest()

    # ハッシュ値を整数に変換し、絵文字リストのインデックスとして使用
    index = int(hash_digest, 16) % len(animal_emojis)

    return animal_emojis[index]


if __name__ == '__main__':
    # 使用例
    input_string1 = "I love animals!"
    input_string2 = "A happy cat."
    input_string3 = "The jungle."

    print(f"'{input_string1}' の動物絵文字: {get_worker_emoji(input_string1)}")
    print(f"'{input_string1}' の動物絵文字: {get_worker_emoji(input_string1)}")
    print(f"'{input_string1}' の動物絵文字: {get_worker_emoji(input_string1)}")
    print(f"'{input_string2}' の動物絵文字: {get_worker_emoji(input_string2)}")
    print(f"'{input_string3}' の動物絵文字: {get_worker_emoji(input_string3)}")
    print(f"'{input_string3}' の動物絵文字: {get_worker_emoji(input_string3)}")
    print(f"'{input_string3}' の動物絵文字: {get_worker_emoji(input_string3)}")
