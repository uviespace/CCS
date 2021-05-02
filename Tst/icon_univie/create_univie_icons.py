import os
import string

uni_grau = '#666666'
uni_weiss = '#ffffff'
uni_schwarz = '#000000'
uni_blau = '#0063A6'

uni_weinrot = '#A71C49'
uni_orangerot = '#DD4814'
uni_goldgelb = '#F6A800'
uni_hellgruen = '#94C154'
uni_mintgruen = '#11897A'

txt_svg = os.path.normpath(os.path.join(os.path.dirname(__file__), 'icon_svg_with_placeholders.txt'))
base_output_folder = os.path.join(os.path.dirname(__file__), 'generated/')

output_folder_2 = 'generated_2_color/'
output_folder_3 = 'generated_3_color/'
output_folder_primary_only = 'generated_primary_only/'
output_folder_primary_text_secondary = 'generated_primary_text_secondary/'
output_folder_all = 'generated_all/'


def set_colors(template, background, frame, univie, text):
    """
    Substitutes the placeholders in the template with the provided hexadecimal color codes
    :param template: the string template
    :param background: color of the background
    :param frame: color of the frame
    :param univie: color of the text 'univie'
    :param text: color of the secondy text
    :return: returns a svg
    """
    svg = template.substitute(color_background=background,
                              color_frame=frame,
                              color_univie=univie,
                              color_text=text)
    return svg


def save_as(data, file_path):
    """
    Makes file_path absolute, creates the directory in file_path and saved the data in the file
    :param data: the data which should be saved
    :param file_path: path to the file where data should be saved (must include file name and extension)
    """
    file_path = os.path.normpath(os.path.join(base_output_folder, file_path))
    os.makedirs(os.path.dirname(file_path), mode=0o777, exist_ok=True)
    with open(file_path, 'w') as file:
        file.write(data)
        file.close()


def remove_hashtags(text):
    """
    Replaces every # with a '' (empty string, to remove) in the text
    :param str text: String where the # should be replaced
    :return: String without #'s
    :rtype: str
    """
    while True:
        quote = text.find('#')
        if quote == -1:
            break
        infront = text[:quote]
        after = text[quote + 1:]
        text = infront + '' + after
    return text


if __name__ == '__main__':
    with open(txt_svg, 'r') as file_obj:
        data = file_obj.read()
        file_obj.close()
        univie_template = string.Template(data)

    primary = [uni_grau, uni_blau, uni_weiss, uni_schwarz]
    secondary = [uni_weinrot, uni_orangerot, uni_goldgelb, uni_hellgruen, uni_mintgruen, uni_grau, uni_blau, uni_weiss, uni_schwarz]

    # using 2 colors, one primary and one secondary
    for background in primary:
        for text in secondary:
            if background != text:
                new_svg = set_colors(univie_template, background, background, text, text)
                new_file_name = 'icon_univie_' + background + '_' + text + '.svg'
                new_file_name = remove_hashtags(new_file_name)
                new_file_name = os.path.join(output_folder_2, new_file_name)
                save_as(new_svg, new_file_name)

    # using 3 colors, two primary, one secondary
    for background in primary:
        for univie in primary:
            for text in secondary:
                if background != univie and background != text:
                    new_svg = set_colors(univie_template, background, background, univie, text)
                    new_file_name = 'icon_univie_' + background + '_' + univie + '_' + text + '.svg'
                    new_file_name = remove_hashtags(new_file_name)
                    new_file_name = os.path.join(output_folder_3, new_file_name)
                    save_as(new_svg, new_file_name)

    # using only primary colors
    for background in primary:
        for frame in primary:
            for univie in primary:
                for text in primary:
                    if background != univie and background != text:
                        new_svg = set_colors(univie_template, background, frame, univie, text)
                        new_file_name = 'icon_univie_' + background + '_' + frame + '_' + univie + '_' + text + '.svg'
                        new_file_name = remove_hashtags(new_file_name)
                        new_file_name = os.path.join(output_folder_primary_only, new_file_name)
                        save_as(new_svg, new_file_name)

    # using primary colors and one secondary as text
    for background in primary:
        for frame in primary:
            for univie in primary:
                for text in secondary:
                    if background != univie and background != text:
                        new_svg = set_colors(univie_template, background, frame, univie, text)
                        new_file_name = 'icon_univie_' + background + '_' + frame + '_' + univie + '_' + text + '.svg'
                        new_file_name = remove_hashtags(new_file_name)
                        new_file_name = os.path.join(output_folder_primary_text_secondary, new_file_name)
                        save_as(new_svg, new_file_name)

    # using primary colors and one secondary as text
    for background in secondary:
        for frame in secondary:
            for univie in secondary:
                for text in secondary:
                    if background != univie and background != text:
                        new_svg = set_colors(univie_template, background, frame, univie, text)
                        new_file_name = 'icon_univie_' + background + '_' + frame + '_' + univie + '_' + text + '.svg'
                        new_file_name = remove_hashtags(new_file_name)
                        new_file_name = os.path.join(output_folder_all, new_file_name)
                        save_as(new_svg, new_file_name)
