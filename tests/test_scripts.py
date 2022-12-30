import pytest
import pathlib
import hashlib

from ibex_imaging_knowledge_base_utilities.reagent_resources_csv_2_md_url import (
    csv_to_md_with_url,
)
from ibex_imaging_knowledge_base_utilities.bib2md import bibfile2md
from ibex_imaging_knowledge_base_utilities.update_index_md_stats import (
    update_index_stats,
)


class BaseTest:
    def setup_method(self):
        # Path to testing data is expected in the following location:
        self.data_path = pathlib.Path(__file__).parent.absolute() / "data"

    def files_md5(self, file_path_list):
        """
        Compute a single/combined md5 hash for a list of files.
        """
        md5 = hashlib.md5()
        for file_name in file_path_list:
            with open(file_name, "rb") as fp:
                for mem_block in iter(lambda: fp.read(128 * md5.block_size), b""):
                    md5.update(mem_block)
        return md5.hexdigest()


class TestCSV2MD(BaseTest):
    @pytest.mark.parametrize(
        "csv_file_name, supporting_material_root_dir, vendor_to_website_json_file_path, result_md5hash",
        [
            (
                "reagent_resources.csv",
                "supporting_material",
                "vendor_urls.json",
                "4a918d9274950a9ce091310cdb2903c2",
            )
        ],
    )
    def test_csv_2_md_with_url(
        self,
        csv_file_name,
        supporting_material_root_dir,
        vendor_to_website_json_file_path,
        result_md5hash,
    ):

        csv_to_md_with_url(
            self.data_path / csv_file_name,
            self.data_path / supporting_material_root_dir,
            self.data_path / vendor_to_website_json_file_path,
        )
        assert (
            self.files_md5([(self.data_path / csv_file_name).with_suffix(".md")])
            == result_md5hash
        )


class TestBib2MD(BaseTest):
    @pytest.mark.parametrize(
        "bib_file_name, csl_file_name, result_md5hash",
        [("publications.bib", "ibex.csl", "61f01467fe88de1f686afcbbd4abaed7")],
    )
    def test_bib_2_md(self, bib_file_name, csl_file_name, result_md5hash, tmp_path):
        # Write the output using the tmp_path fixture
        output_file_path = tmp_path / "publications.md"
        bibfile2md(
            self.data_path / bib_file_name,
            self.data_path / csl_file_name,
            output_file_path,
        )
        assert self.files_md5([output_file_path]) == result_md5hash


class TestUpdateIndexMDStats(BaseTest):
    @pytest.mark.parametrize(
        "input_md_file_name, csv_file_name, result_md5hash",
        [("index.md.in", "reagent_resources.csv", "4bb071331c7fe7945e0759e9c95bbd12")],
    )
    def test_update_index_stats(
        self, input_md_file_name, csv_file_name, result_md5hash, tmp_path
    ):
        # Write the output using the tmp_path fixture
        output_file_path = tmp_path / input_md_file_name
        update_index_stats(
            self.data_path / input_md_file_name,
            self.data_path / csv_file_name,
            output_file_path,
        )
        assert self.files_md5([output_file_path]) == result_md5hash
