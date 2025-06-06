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

import pandas as pd
import argparse
import sys
from ibex_imaging_knowledge_base_utilities.argparse_types import (
    file_path_endswith,
    dir_path,
)
from .utilities import _dataframe_2_md

"""
This script converts the IBEX knowledge-base fluorescent_probes.csv file to markdown.

This script is automatically run when modifications to the fluorescent_probes.csv file is merged
into the main branch of the ibex_knowledge_base repository (see .github/workflows/data2md.yml).

Assumption: The fluorescent_probes.csv file is valid. It conforms to the expected format (empty entries denoted
by the string "NA").
"""


def fluorescent_probe_csv_to_md(template_file_path, csv_file_path, output_dir):
    """
    Convert the IBEX knowledge-base fluorescent probe csv file to markdown. Output is written to a
    file named fluorescent_probes.md in the output directory. The template_file_path file is expected
    to contain the string
    {probe_table} which is replaced with the contents of the actual table.
    """
    # Read the dataframe and keep entries that are "NA", don't convert to nan
    df = pd.read_csv(csv_file_path, dtype=str, keep_default_na=False)
    df.sort_values(by=["Excitation Max (nm)", "Emission Max (nm)"], inplace=True)
    with open(template_file_path, "r") as fp:
        input_md_str = fp.read()
    with open(output_dir / template_file_path.stem, "w") as fp:
        fp.write(
            input_md_str.format(
                probe_table=_dataframe_2_md(
                    df, index=False, colalign=["left"] * len(df.columns)
                )
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert knowledge-base fluorescent probes file from csv to md and sort according to excitation and emission."  # noqa E501
    )
    parser.add_argument(
        "md_template_file",
        type=lambda x: file_path_endswith(x, ".md.in"),
        help='Path to template markdown file which contains the string "{probe_table}".',
    )
    parser.add_argument(
        "csv_file",
        type=lambda x: file_path_endswith(x, ".csv"),
        help="Path to the fluorescent_probes.csv file.",
    )
    parser.add_argument(
        "output_dir",
        type=dir_path,
        help="Path to the output directory (the fluorescent_probes.md file is written to this directory).",
    )
    args = parser.parse_args(argv)

    try:
        return fluorescent_probe_csv_to_md(
            template_file_path=args.md_template_file,
            csv_file_path=args.csv_file,
            output_dir=args.output_dir,
        )
    except Exception as e:
        print(
            f"{e}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
