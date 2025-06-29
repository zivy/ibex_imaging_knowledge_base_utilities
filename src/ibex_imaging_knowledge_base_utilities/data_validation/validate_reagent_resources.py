# =========================================================================
#
#  Copyright Ziv Yaniv
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0.txt
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# =========================================================================

import sys
import json
import argparse
import pandas as pd
import pathlib
import re
import os
from ibex_imaging_knowledge_base_utilities.argparse_types import (
    file_path_endswith,
    dir_path,
    csv_path,
)
from .utilities import validate_df, md5sum

"""
This script validates the contents of the reagents_resources.csv file:
1. Perform basic validation (see validate_basic.py script and reagent_resources.json configuration file).
2. Ensure that the ORCIDs from the contributors and agree and disagree columns are all listed in the .zenodo.json file.
3. Ensure there are no repeated rows.
4. Ensure that the contributor ORCID appears in either the agree or disagree column.
5. Ensure that number of ORCIDS in the agree/disagree columns is less than the MAX_ORCID_ENTRIES=5 (we don't accept more
   than this number of reagent validation reproductions).
6. Ensure that the information in the supporting material files is consistent with the content of the
   reagent_resources.csv.
7. Ensure there are no superfluous files in the supporting_material directory. These are files that are not
   associated with information in the reagent_resources.csv, they shouldn't be there. The expected files are
   either markdown files associated with the target_conjugate/orcid.md combination or listed image files.
8. Ensure that the listed image files exist and are valid (match their listed md5 hash).
"""


def validate_reagent_resources(
    csv_file_name,
    json_config_file_name,
    zenodo_json_file_name,
    vendors_csv_file_name,
    supporting_material_root_dir,
):
    MAX_ORCID_ENTRIES = 5
    # shift the index number which is zero based and ignores the header so that the returned
    # row numbers match what you would see in a spreadsheet editor (e.g. excell, google docs)
    shift_index = 2

    df = pd.read_csv(csv_file_name, dtype=str, keep_default_na=False)
    # Check that there are no empty cells. An empty entry should be explicitly marked by "NA". This
    # ensures that the data provider intentionally marked the cell as empty.
    empty_cells = df.map(lambda x: x.strip()) == ""
    problematic_cells = []
    for c in empty_cells.columns:
        empty_cell_indexes = empty_cells[c][empty_cells[c]].index
        if not empty_cell_indexes.empty:
            problematic_cells.append([c, empty_cell_indexes + shift_index])
    if problematic_cells:
        print(
            f"The following cells are empty, please replace with NA, (column, rows): {problematic_cells}",
            file=sys.stderr,
        )
        return 1

    with open(json_config_file_name) as fp:
        configuration_dict = json.load(fp)

    # Get the list of contributor ORCIDs from the .zenodo.json file and
    # enforce that contributors listed in the contributor/agree/disagree columns are there.
    # Assume the zenodo file has been validated, so ORCID information is
    # available.
    with open(zenodo_json_file_name) as fp:
        zenodo_dict = json.load(fp)
    orcids = [data["orcid"].strip() for data in zenodo_dict["creators"]] + ["NA"]

    # Get the list of vendor names from the vendor_urls.csv file name, column
    # titled "Vendor"
    vendor_names = pd.read_csv(vendors_csv_file_name)["Vendor"].to_list()

    # Add the ORCIDs and vendor names to the configuration dictionary to
    # enforce column content to be in a set of values
    if "column_is_in" in configuration_dict:
        configuration_dict["column_is_in"]["Contributor"] = orcids
        configuration_dict["column_is_in"]["Vendor"] = vendor_names
    else:
        configuration_dict["column_is_in"] = {"Contributor": orcids}
        configuration_dict["column_is_in"] = {"Vendor": vendor_names}

    if "multi_value_column_is_in" in configuration_dict:
        configuration_dict["multi_value_column_is_in"]["Agree"] = orcids
        configuration_dict["multi_value_column_is_in"]["Disagree"] = orcids
    else:
        configuration_dict["multi_value_column_is_in"] = {
            "Agree": orcids,
            "Disagree": orcids,
        }

    res = validate_df(df, **configuration_dict)
    # check if basic validation failed
    if res != 0:
        return res

    # Check for repeated rows (ignore the columns associated with contributor's details)
    raw_df = df.drop(["Contributor", "Agree", "Disagree"], axis=1)
    all_duplicates = raw_df[raw_df.duplicated(keep=False)]
    duplicated_indexes = all_duplicates.groupby(
        list(all_duplicates), group_keys=True
    ).apply(lambda x: tuple(x.index), include_groups=False)
    if not duplicated_indexes.empty:
        duplicated_indexes = [
            [i + shift_index for i in indexes] for indexes in duplicated_indexes
        ]
        print(
            f"The following rows are duplicates: {duplicated_indexes}", file=sys.stderr
        )
        return 1

    # Check that the Contributor ORCID appears in the Agree or Disagree column.
    # In most cases it will be in the Agree column. When the recommendation
    # is refuted (multiple validators disagreed with the original contributor)
    # and changed from Yes to No or vice versa the ORCIDs from the Agree and
    # Disagree columns are swapped and the original contributors ORCID will appear
    # in the Disagree column.
    df["Agree"] = df["Agree"].apply(
        lambda x: [v.strip() for v in x.split(";") if v.strip() not in ["", "NA"]]
    )
    df["Disagree"] = df["Disagree"].apply(
        lambda x: [v.strip() for v in x.split(";") if v.strip() not in ["", "NA"]]
    )
    problem_row_indexes = df.index[
        df[["Contributor", "Agree", "Disagree"]].apply(
            lambda x: not (x.iloc[0] in x.iloc[1] + x.iloc[2]), axis=1
        )
    ]
    if not problem_row_indexes.empty:
        problem_row_indexes = [i + shift_index for i in problem_row_indexes]
        print(
            "The 'Contributor' in the following rows does not appear in the 'Agree' or 'Disagree' columns "
            + f"as expected: {problem_row_indexes}",
            file=sys.stderr,
        )
        return 1
    # Check that the number of ORCIDs in the Agree and Disagree columns is equal/less than MAX_ORCID_ENTRIES
    problem_row_indexes = df.index[
        df[["Agree", "Disagree"]].apply(
            lambda x: len(x.iloc[0]) > MAX_ORCID_ENTRIES
            or len(x.iloc[1]) > MAX_ORCID_ENTRIES,
            axis=1,
        )
    ]
    if not problem_row_indexes.empty:
        problem_row_indexes = [i + shift_index for i in problem_row_indexes]
        print(
            "The number of ORCIDs in either the 'Agree' or 'Disagree' column for the following rows "
            + f"is larger than the maximal allowed ({MAX_ORCID_ENTRIES}): {problem_row_indexes}",
            file=sys.stderr,
        )
        return 1

    # Check that the same ORCID does not appear both in the Agree and Disagree columns
    problem_row_indexes = df.index[
        df[["Agree", "Disagree"]].apply(
            lambda x: bool(set(x.iloc[0]).intersection(x.iloc[1])), axis=1
        )
    ]
    if not problem_row_indexes.empty:
        problem_row_indexes = [
            [i + shift_index for i in indexes] for indexes in problem_row_indexes
        ]
        print(
            "One or more ORCIDs in the following rows appears both in the 'Agree' and 'Disagree' "
            + f"column for the same validation: {problem_row_indexes}",
            file=sys.stderr,
        )
        return 1

    # Check that the information in the supporting material files is consistent with the content of
    # the reagent_resources.csv.

    # Split the semicolon separated strings into lists
    df[["Image Files", "Captions", "MD5"]] = df[["Image Files", "Captions", "MD5"]].map(
        lambda x: [] if x.strip() == "NA" else [v.strip() for v in x.split(";")]
    )

    unique_target_conjugate = df[
        ["Target Name / Protein Biomarker", "Conjugate"]
    ].drop_duplicates()

    res = unique_target_conjugate.apply(
        lambda target_conjugate: validate_supporting_material(
            target_conjugate, df, supporting_material_root_dir, shift_index
        ),
        axis=1,
    )
    md_file_paths_from_csv = set()
    status = 0
    for fnames, s in res:
        if s != 0:
            status = 1
        md_file_paths_from_csv.update(fnames)
    if status != 0:
        return 1
    md_file_paths_from_supporting_material_dir = set(
        pathlib.Path(supporting_material_root_dir).rglob("*.md")
    )
    superfluous_md_files = md_file_paths_from_supporting_material_dir.difference(
        md_file_paths_from_csv
    )
    if superfluous_md_files:
        print(
            "The following md files are superfluous to those expected from the "
            + f"reagent_resources.csv: {superfluous_md_files}",
            file=sys.stderr,
        )
        return 1

    # Check the image information (files exits, match md5 hashes, configurations for same image
    # match, no images in supporting material directory that aren't listed in the reagent_resource.csv)
    return validate_images(
        df[["Image Files", "Captions", "MD5"]],
        supporting_material_root_dir,
        shift_index,
    )


def replace_char_list(input_str, change_chars_list, replacement_char):
    """
    Given an input string replace all characters that are in the change_char_list to the replacement_char.
    """
    for c in change_chars_list:
        if c in input_str:
            input_str = input_str.replace(c, replacement_char)
    return input_str


def validate_images(df, supporting_material_root_dir, shift_index):
    supporting_material_root_dir_abspath = os.path.abspath(supporting_material_root_dir)
    image_file_abspaths = df["Image Files"].apply(
        lambda x: [os.path.join(supporting_material_root_dir_abspath, v) for v in x]
    )
    # check that number of files, captions and md5 hashes is equal per configuration/line
    problem_rows = df.apply(
        lambda x: (len(x.iloc[0]) != len(x.iloc[1]))
        or (len(x.iloc[1]) != len(x.iloc[2])),
        axis=1,
    )
    problem_row_indexes = problem_rows[problem_rows].index
    if not problem_row_indexes.empty:
        problem_row_indexes = [i + shift_index for i in problem_row_indexes]
        print(
            "The number of 'Image Files', 'Captions' and 'MD5' hashes is not equal "
            + f"in the following rows: {problem_row_indexes}",
            file=sys.stderr,
        )
        return 1

    # Check that image files exist and match the listed md5 hash
    missing_file_row_indexes_name = []
    md5_mismatch_file_row_indexes_name = []
    for i, (file_list, md5_list) in enumerate(
        zip(image_file_abspaths, df["MD5"]), start=shift_index
    ):
        for f, md5 in zip(file_list, md5_list):
            if not os.path.isfile(f):
                missing_file_row_indexes_name.append((i, f))
            elif md5sum(f) != md5:
                md5_mismatch_file_row_indexes_name.append((i, f))
    if missing_file_row_indexes_name:
        print(
            f"The following image files do not exist (row_number, file_name): {missing_file_row_indexes_name}",
            file=sys.stderr,
        )
    if md5_mismatch_file_row_indexes_name:
        print(
            "The following image files do not match the listed md5 hash "
            + f"(row_number, file_name): {md5_mismatch_file_row_indexes_name}",
            file=sys.stderr,
        )
    if missing_file_row_indexes_name or md5_mismatch_file_row_indexes_name:
        return 1
    # List of files that may be in the supporting_materials directory
    # structure and that we should ignore when comparing to the list of
    # images found in the reagent_resources.csv.
    # The supporting materials directory is expected to contain markdown
    # files with file extension ".md" and all other files are assumed to
    # be images.
    FILES_IGNORE = [".DS_Store"]

    # Get all the non markdown file names and make sure that they match those in
    # the image_resources.csv. The supporting material subdirectory is expected
    # to contain markdown files and images, no other files.
    image_file_paths_from_supporting_material_dir = []
    for dir_name, subdir_names, file_names in os.walk(supporting_material_root_dir):
        for file in file_names:
            if not file.endswith(".md") and file not in FILES_IGNORE:
                image_file_paths_from_supporting_material_dir.append(
                    os.path.join(os.path.abspath(dir_name), file)
                )
    image_file_paths_from_supporting_material_dir = set(
        image_file_paths_from_supporting_material_dir
    )
    all_csv_image_files = []
    for image_file_list in image_file_abspaths:
        all_csv_image_files.extend(image_file_list)
    image_file_paths_from_csv = set(all_csv_image_files)
    superfluous_image_files = image_file_paths_from_supporting_material_dir.difference(
        image_file_paths_from_csv
    )
    if superfluous_image_files:
        print(
            "The following files are superfluous to those expected from the "
            + f"contents of the image_resources.csv file: {superfluous_image_files}",
            file=sys.stderr,
        )
        return 1
    return 0


def validate_supporting_material(
    target_conjugate, all_df, supporting_material_root_dir, shift_index
):
    """
    Given a specific pair of target-conjugate and the complete reagent resources dataframe, go
    over the supporting material files for all orcids listed in the dataframe and validate that
    the contents of the configurations listed in the supporting material files match the contents
    of the reagent resources file.
    Returns tuple:(list of supporting material markdown files that were validated, status)
    """
    # List of characters that will be replaced with an underscore. Some of these are invalid
    # in file paths in windows/linux/osx and some don't work well when they appear in file
    # paths used by jekyll and GitHub to create a static page. We replace all of them with
    # an underscore.
    invalid_chars = [
        " ",
        "\t",
        "/",
        "\\",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "<",
        ">",
        ":",
        "&",
    ]

    status = 0
    # The target_conjugate.index contains the column names
    tc_rows = all_df[
        (all_df[target_conjugate.index[0]] == target_conjugate.iloc[0])
        & (all_df[target_conjugate.index[1]] == target_conjugate.iloc[1])
    ]
    # Get all the orcids associated with this target_conjugate pair
    orcids = set().union(*(pd.concat([tc_rows["Agree"], tc_rows["Disagree"]])))
    if "NA" in orcids:
        orcids.remove("NA")

    data_path = supporting_material_root_dir / pathlib.Path(
        replace_char_list(
            input_str=f"{target_conjugate.iloc[0]}_{target_conjugate.iloc[1]}",
            change_chars_list=invalid_chars,
            replacement_char="_",
        )
    )
    # Get all the image file names, their captions and line index in which they appear.
    # An image is required to appear in one or more of the supporting material files
    # associated with the ORCIDs for this target_conjugate combination
    image_file_name_caption_index = []
    for image_fnames, image_captions, i in zip(
        tc_rows["Image Files"], tc_rows["Captions"], tc_rows.index
    ):
        image_file_name_caption_index.extend(
            list(zip(image_fnames, image_captions, [i] * len(image_fnames)))
        )

    file_names = []
    for orcid in orcids:
        md_file_path = data_path / pathlib.Path(orcid + ".md")
        file_names.append(md_file_path)
        if not md_file_path.is_file():
            print(f"{md_file_path} does not exist.", file=sys.stderr)
            status = 1
            continue  # expected file is missing, can't compare contents to the reagent_resources.csv
        orcid_configurations = tc_rows[
            tc_rows["Agree"].apply(lambda x: orcid in x)
            | tc_rows["Disagree"].apply(lambda x: orcid in x)
        ]
        # Convert entries to sets so that we can compare with the contents of the supporting
        # material files ignoring the order of the orcids (list equality checks is not invariant to order)
        orcid_configurations["Agree"] = orcid_configurations["Agree"].apply(
            lambda x: frozenset(x)
        )
        orcid_configurations["Disagree"] = orcid_configurations["Disagree"].apply(
            lambda x: frozenset(x)
        )
        try:
            # read file content
            with open(md_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Check that images and captions specified in the reagent_resources csv
            # are used in the supporting material files, remove those that are used
            # for this ORCID. At the end of the process we expect the final list to
            # be empty.
            image_file_name_caption_index = [
                [image_fname, image_caption, i]
                for image_fname, image_caption, i in image_file_name_caption_index
                if (pathlib.Path(image_fname).name not in content)
                or (image_caption not in content)
            ]
            # remove all rows that are only whitespace and
            # remove leading or trailing whitespace from all other rows
            content = [c.strip() for c in content.split("\n") if c.strip()]
            # Get configurations table, this needs to match the information in the csv file
            config_start_section = content.index("# Configurations") + 1
            config_end_section = content.index("# Publications")
            columns = [
                column.strip()
                for column in content[config_start_section].split("|")
                if column.strip()
            ]
            table_content = []
            for r_index in range(config_start_section + 2, config_end_section):
                # split the table columns and get rid of the preceding and trailing strings that correspond to table
                # borders '|'
                table_content.append(
                    [rc.strip() for rc in content[r_index].split("|")][1:-1]
                )
            # Create dataframe from markdown table and drop the notes column which is part of the
            # supporting material table but isn't in the reagent_resources.csv
            supporting_orcid_configurations = pd.DataFrame(
                data=table_content, columns=columns
            ).drop(["Notes"], axis=1)

            # The ORCID structure is NNNN-NNNN-NNNN-NNN[N|X] where N is a digit
            # and the last characters is either a digit or the letter X
            # see https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
            # for details
            # Get all the ORCIDs that are in square brackets, these are what is displayed by the markdown and
            # then remove the square brackets and create a set from them so that we can easily compare for equality
            # to the reagent_resources ORCIDs without caring about order of appearance
            orcid_pattern = re.compile(r"\[\d{4}-\d{4}-\d{4}-\d{3}[\dX]\]")
            supporting_orcid_configurations["Agree"] = supporting_orcid_configurations[
                "Agree"
            ].apply(
                lambda x: frozenset([s[1:-1] for s in re.findall(orcid_pattern, x)])
            )
            supporting_orcid_configurations[
                "Disagree"
            ] = supporting_orcid_configurations["Disagree"].apply(
                lambda x: frozenset([s[1:-1] for s in re.findall(orcid_pattern, x)])
            )
            supporting_orcid_configurations["Contributor"] = (
                supporting_orcid_configurations["Contributor"].apply(
                    lambda x: re.findall(orcid_pattern, x)[0][1:-1]
                )
            )
            # Compare the configuration data from the supporting material to that from the reagent_resources file.
            # We don't use DataFrame.equal because that assumes the order of the columns and indexes is the same,
            # which is a harder constraint than needed.

            # Drop the columns that are not part of the table in the markdown file from the csv based dataframe.
            orcid_configurations = orcid_configurations.drop(
                ["Image Files", "Captions", "MD5"], axis=1
            )
            # The two dataframes are equivalent if they have the same length and contain the same rows, irrespective
            # of the row order
            if (len(supporting_orcid_configurations) != len(orcid_configurations)) or (
                len(
                    pd.concat(
                        [supporting_orcid_configurations, orcid_configurations]
                    ).drop_duplicates()
                )
                != len(supporting_orcid_configurations)
            ):
                print(
                    f"Contents of ({md_file_path}) do not match the contents of the reagent_resources.csv",
                    file=sys.stderr,
                )
                status = 1
        except Exception as e:
            print(f"file:{md_file_path}, exception: {e}", file=sys.stderr)
            status = 1
    if image_file_name_caption_index:
        status = 1
        for image_fname, image_caption, i in image_file_name_caption_index:
            print(
                f"Image information, caption ({image_caption}) or filename ({image_fname}), "
                + "listed in the reagent_resources.csv line "
                + f"({i+shift_index}) is not used in supporting material file ({md_file_path}).",
                file=sys.stderr,
            )

    return (file_names, status)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validation of reagent_resources.csv file."
    )
    parser.add_argument(
        "csv_file",
        type=lambda x: file_path_endswith(x, ".csv"),
        help="Reagent resources csv file to validate.",
    )
    parser.add_argument(
        "json_config_file",
        type=lambda x: file_path_endswith(x, ".json"),
        help="Configuration file for basic validation.",
    )
    parser.add_argument(
        "zenodo_json_file",
        type=lambda x: file_path_endswith(x, ".json"),
        help=".zenodo.json file which contains the ORCIDs of all contributors.",
    )
    parser.add_argument(
        "vendors_csv_file",
        type=lambda x: csv_path(x, required_columns={"Vendor"}),
        help="csv file containing all valid vendor names in a column titled 'Vendor'.",
    )
    parser.add_argument(
        "supporting_material_root_dir",
        type=dir_path,
        help="Path to supporting material root directory.",
    )

    args = parser.parse_args(argv)
    return validate_reagent_resources(
        args.csv_file,
        args.json_config_file,
        args.zenodo_json_file,
        args.vendors_csv_file,
        args.supporting_material_root_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
