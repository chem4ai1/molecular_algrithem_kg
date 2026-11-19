import pandas as pd
import requests
import time
import os
import requests
import gzip
from sklearn.utils import shuffle


def holdout_split(df: pd.DataFrame, percentage: float, random_state: int = 42):
    """
    Perform a holdout split on a DataFrame.

    Args:
        df (pd.DataFrame): The input DataFrame to split.
        percentage (float): The proportion of the data to be in the test set (e.g., 0.2 for 20%).

    Returns:
        pd.DataFrame, pd.DataFrame: The training and test DataFrames.
    """

    # Shuffle the DataFrame
    df = shuffle(df, random_state=random_state).reset_index(drop=True)

    # Calculate the split index
    split_index = int(len(df) * (1 - percentage))

    # Split the DataFrame
    train_df = df[:split_index]
    test_df = df[split_index:]
    return train_df, test_df


def merge_dataset(onto_1_path: str, onto_2_path: str) -> pd.DataFrame:
    onto_1 = pd.read_csv(onto_1_path, sep="\t", header=None)
    onto_2 = pd.read_csv(onto_2_path, sep="\t", header=None)
    onto = pd.concat([onto_1, onto_2]).drop_duplicates().reset_index(drop=True)
    return onto


def ensure_file_exists(
    file_name: str = "fb2w.nt",
    download_url: str = "https://storage.googleapis.com/freebase-public/fb2w.nt.gz",
):
    """
    Checks if a file exists at the given path. If not, downloads it from the specified URL.

    Args:
        file_path (str): Path to the file to check.
        download_url (str): URL to download the file if it does not exist.

    Returns:
        str: Path to the file.
    """
    file_path = os.path.abspath(os.path.join("./data", file_name))
    if os.path.exists(file_path):
        print(f"File {file_path} found !")
        return file_path

    file_path = os.path.abspath(os.path.join("./data", file_name + ".gz"))
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        print(f"Downloading from: {download_url}")

        # Ensure the parent directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            # Download the file
            response = requests.get(download_url, stream=True)
            response.raise_for_status()  # Raise an HTTPError for bad responses

            # Save the file
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            print(f"File downloaded successfully: {file_path}")
            # here on
            print(f"Extracting file: {file_path}")
            if not file_path.endswith(".gz"):
                print(f"Error: The file {file_path} is not a .gz file.")
                return

            decompressed_file_path = file_path[:-3]  # Remove the .gz extension

            try:
                with gzip.open(file_path, "rb") as gz_file:
                    with open(decompressed_file_path, "wb") as decompressed_file:
                        decompressed_file.write(gz_file.read())

                print(f"File decompressed successfully: {decompressed_file_path}")
                return decompressed_file_path
            except Exception as e:
                print(f"Error decompressing file: {e}")

        except Exception as e:
            print(f"Error downloading the file: {e}")
            raise
    else:
        print(f"File already exists: {file_path}")


def convert_fb_id(fb_id):
    """Converts Freebase ID from /m/ format to m. format."""
    if fb_id.startswith("/m/"):
        return "m." + fb_id[3:]
    elif fb_id.startswith("/en/"):
        return "en." + fb_id[4:]
    else:
        return fb_id


def extract_entities(files_path, filenames):
    """Extracts all unique entities from the specified files."""
    entities = set()
    for filename in filenames:
        if os.path.isfile(os.path.join(files_path, filename)):
            print(f"Reading file {os.path.join(files_path, filename)}")
            file_path = os.path.join(files_path, filename)
            df = pd.read_csv(
                file_path,
                sep="\t",
                header=None,
                names=["entity1", "relation", "entity2"],
            )
            entities.update(df["entity1"].unique())
            entities.update(df["entity2"].unique())
        else:
            print(f" File {os.path.join(files_path, filename)} not found! \n")
    return entities


def create_mapping(entities_to_map, mapping_file_path):
    """Creates a mapping from Freebase IDs to Wikidata IDs for the given entities."""
    fb_to_wd = {}
    entities_converted = {convert_fb_id(e) for e in entities_to_map}
    with open(mapping_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            subj, pred, obj = parts[0], parts[1], parts[2]
            if (
                subj.startswith("<")
                and subj.endswith(">")
                and obj.startswith("<")
                and obj.endswith(">")
            ):
                fb_uri = subj[1:-1]
                wd_uri = obj[1:-1]
                if fb_uri.startswith("http://rdf.freebase.com/ns/"):
                    fb_id = fb_uri[len("http://rdf.freebase.com/ns/") :]
                    if fb_id in entities_converted:
                        if wd_uri.startswith("http://www.wikidata.org/entity/"):
                            wd_id = wd_uri[len("http://www.wikidata.org/entity/") :]
                            fb_to_wd[fb_id] = wd_id
        print(f"Total mapped entities: {len(fb_to_wd)}")
    return fb_to_wd


def get_entities_info(wd_ids, language="en"):
    """Fetches labels and 'instance of' (P31) statements for the given Wikidata IDs."""
    entity_labels = {}
    entity_instance_of = {}
    instance_of_value_ids = set()

    batch_size = 50
    url = "https://www.wikidata.org/w/api.php"

    for i in range(0, len(wd_ids), batch_size):
        batch_ids = wd_ids[i : i + batch_size]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch_ids),
            "format": "json",
            "languages": language,
            "props": "labels|claims",
        }
        try:
            response = requests.get(url, params=params)
            data = response.json()
            entities = data.get("entities", {})
            for wd_id, entity in entities.items():
                # Get label
                label = entity.get("labels", {}).get(language, {}).get("value", "")
                entity_labels[wd_id] = label
                # Get 'instance of' statements
                claims = entity.get("claims", {})
                p31_claims = claims.get("P31", [])
                instance_of_ids = []
                for claim in p31_claims:
                    mainsnak = claim.get("mainsnak", {})
                    datavalue = mainsnak.get("datavalue", {})
                    if datavalue.get("type") == "wikibase-entityid":
                        value_id = datavalue.get("value", {}).get("id")
                        if value_id:
                            instance_of_ids.append(value_id)
                            instance_of_value_ids.add(value_id)
                entity_instance_of[wd_id] = instance_of_ids
        except Exception as e:
            print(f"Error fetching entities info for IDs {batch_ids}: {e}")
        time.sleep(0.1)  # Be polite to the API
    return entity_labels, entity_instance_of, instance_of_value_ids


def get_labels(wd_ids, language="en"):
    """Fetches labels for the given Wikidata IDs using the Wikidata API."""
    labels = {}
    batch_size = 50
    url = "https://www.wikidata.org/w/api.php"
    for i in range(0, len(wd_ids), batch_size):
        batch_ids = wd_ids[i : i + batch_size]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch_ids),
            "format": "json",
            "languages": language,
            "props": "labels",
        }
        try:
            response = requests.get(url, params=params)
            data = response.json()
            entities = data.get("entities", {})
            for wd_id, entity in entities.items():
                label = entity.get("labels", {}).get(language, {}).get("value", "")
                labels[wd_id] = label
        except Exception as e:
            print(f"Error fetching labels for IDs {batch_ids}: {e}")
        time.sleep(0.1)  # Be polite to the API
    return labels


def save_mapping(fb_to_wd, output_path):
    """Saves the Freebase to Wikidata ID mappings to a TSV file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for fb_id, wd_id in fb_to_wd.items():
            original_fb_id = "/m/" + fb_id[2:] if fb_id.startswith("m.") else fb_id
            f.write(f"{original_fb_id}\t{wd_id}\n")


def save_labels(fb_to_wd, entity_labels, output_path):
    """Saves the Freebase IDs and their corresponding labels to a TSV file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for fb_id, wd_id in fb_to_wd.items():
            label = entity_labels.get(wd_id, "")
            original_fb_id = "/m/" + fb_id[2:] if fb_id.startswith("m.") else fb_id
            f.write(f"{original_fb_id}\t{label}\n")


def read_type_mapping(type_mapping_path):
    """Reads type_mapping.tsv and returns label to Wikidata ID mappings."""
    label_to_wd_id = {}
    with open(type_mapping_path, "r", encoding="utf-8") as f:
        for line in f:
            label, url = line.strip().split("\t")
            wd_id = url.split("/")[-1]
            label_to_wd_id[label] = wd_id
    return label_to_wd_id


def fetch_claims(wd_ids, language="en"):
    """Fetches claims for a list of Wikidata IDs."""
    claims_data = {}
    batch_size = 50
    url = "https://www.wikidata.org/w/api.php"

    for i in range(0, len(wd_ids), batch_size):
        batch_ids = wd_ids[i : i + batch_size]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch_ids),
            "format": "json",
            "languages": language,
            "props": "claims",
        }
        try:
            response = requests.get(url, params=params)
            data = response.json()
            entities = data.get("entities", {})
            for wd_id, entity in entities.items():
                claims = entity.get("claims", {})
                claims_data[wd_id] = claims
        except Exception as e:
            print(f"Error fetching claims for IDs {batch_ids}: {e}")
        time.sleep(0.1)  # Be polite to the API
    return claims_data


def get_labels_for_ids(wd_ids, language="en"):
    """Fetches labels for a list of Wikidata IDs."""
    labels = {}
    batch_size = 50
    url = "https://www.wikidata.org/w/api.php"

    for i in range(0, len(wd_ids), batch_size):
        batch_ids = wd_ids[i : i + batch_size]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch_ids),
            "format": "json",
            "languages": language,
            "props": "labels",
        }
        try:
            response = requests.get(url, params=params)
            data = response.json()
            entities = data.get("entities", {})
            for wd_id, entity in entities.items():
                label = entity.get("labels", {}).get(language, {}).get("value", "")
                labels[wd_id] = label
        except Exception as e:
            print(f"Error fetching labels for IDs {batch_ids}: {e}")
        time.sleep(0.1)
    return labels


def create_ontology(type_mapping_path, output_ontology_path):
    """Creates the ontology.tsv file as per the specifications."""
    # Step 1: Read type_mapping.tsv
    label_to_wd_id = read_type_mapping(type_mapping_path)
    wd_id_to_label = {v: k for k, v in label_to_wd_id.items()}
    type_labels_set = set(label_to_wd_id.keys())
    type_wd_ids = list(label_to_wd_id.values())

    # Step 2: Fetch claims for each type
    claims_data = fetch_claims(type_wd_ids)

    # Step 3: Collect all property IDs and value IDs
    property_ids = set()
    value_ids = set()
    for claims in claims_data.values():
        for prop_claims in claims.values():
            for claim in prop_claims:
                # Property ID is the key in the claims dict (e.g., 'P279')
                # Value ID is in the mainsnak of the claim
                mainsnak = claim.get("mainsnak", {})
                datavalue = mainsnak.get("datavalue", {})
                if datavalue.get("type") == "wikibase-entityid":
                    value_id = datavalue.get("value", {}).get("id")
                    if value_id:
                        value_ids.add(value_id)
                # Add property ID
                property_id = mainsnak.get("property")
                if property_id:
                    property_ids.add(property_id)

    # Step 4: Fetch labels for property IDs and value IDs
    all_ids_to_fetch = list(property_ids.union(value_ids))
    id_to_label = get_labels_for_ids(all_ids_to_fetch)

    # Step 5: Open the output file for writing
    with open(output_ontology_path, "w", encoding="utf-8") as ontology_file:
        # Step 6: For each type, process its claims
        for wd_id, claims in claims_data.items():
            starting_type_label = wd_id_to_label.get(wd_id, "")
            if not starting_type_label:
                continue  # Skip if label is missing
            for prop_id, prop_claims in claims.items():
                property_label = id_to_label.get(prop_id, "")
                for claim in prop_claims:
                    mainsnak = claim.get("mainsnak", {})
                    datavalue = mainsnak.get("datavalue", {})
                    if datavalue.get("type") == "wikibase-entityid":
                        value_id = datavalue.get("value", {}).get("id")
                        value_label = id_to_label.get(value_id, "")
                        # Check if the value label is in type_mapping.tsv
                        if value_label in type_labels_set:
                            # Write to ontology.tsv
                            ontology_file.write(
                                f"{starting_type_label}\t{property_label}\t{value_label}\n"
                            )


def main(
    files_path,
    mapping_file_path,
    output_mapping_path,
    output_labels_path,
    output_type_path,
    output_type_mapping_path,
    output_ontology_path,
):
    """Main function to orchestrate the mapping and label extraction."""
    filenames = ["train.txt", "valid.txt", "test.txt"]
    # Step 1: Extract entities
    all_entities = extract_entities(files_path, filenames)

    # Step 2: Create mapping for extracted entities
    fb_to_wd = create_mapping(all_entities, mapping_file_path)

    # Step 3: Save the mapping to a file
    save_mapping(fb_to_wd, output_mapping_path)

    # Step 4: Get labels and 'instance of' statements for the mapped Wikidata IDs
    wd_ids = list(set(fb_to_wd.values()))
    entity_labels, entity_instance_of, instance_of_value_ids = get_entities_info(wd_ids)

    # Step 5: Save the labels to a file
    save_labels(fb_to_wd, entity_labels, output_labels_path)

    # Step 6: Get labels for 'instance of' values
    instance_of_labels = get_labels(list(instance_of_value_ids))

    # Step 7: Save 'type.tsv' and 'type_mapping.tsv'
    # 'type.tsv' columns: freebase_entity_id, 'type', label_of_value
    # 'type_mapping.tsv' columns: label_of_value, full_URL_of_value

    # Open files for writing
    with open(output_type_path, "w", encoding="utf-8") as type_file, open(
        output_type_mapping_path, "w", encoding="utf-8"
    ) as type_mapping_file:

        type_mappings = {}
        for fb_id, wd_id in fb_to_wd.items():
            instance_of_ids = entity_instance_of.get(wd_id, [])
            for value_id in instance_of_ids:
                label_of_value = instance_of_labels.get(value_id, "")
                full_URL_of_value = "https://www.wikidata.org/wiki/" + value_id

                # Write to 'type.tsv'
                original_fb_id = "/m/" + fb_id[2:] if fb_id.startswith("m.") else fb_id
                type_file.write(f"{original_fb_id}\ttype\t{label_of_value}\n")

                # Add to type_mappings
                if label_of_value not in type_mappings:
                    type_mappings[label_of_value] = full_URL_of_value

        # Write 'type_mapping.tsv'
        for label, url in type_mappings.items():
            type_mapping_file.write(f"{label}\t{url}\n")

    # Step 8: Create 'ontology.tsv' using 'type_mapping.tsv'
    create_ontology(output_type_mapping_path, output_ontology_path)


# if __name__ == "__main__":
#     dataset_name = 'fb237'
#     versions = ['v1', 'v1_ind', 'v2', 'v2_ind', 'v3', 'v3_ind', 'v4', 'v4_ind']
#     mapping_file_path = ensure_file_exists()
#
#     for version in versions:
#         df_name = dataset_name + '_' + version
#         files_path = os.path.abspath(os.path.join('./data', df_name))
#
#         print(f" Current Dataset {files_path} ")
#
#         # check if the current dataset_directory_exists:
#         if not os.path.exists(files_path):
#             print(f" Dataset {files_path} not found.. \t SKIPPING")
#             continue
#
#         # mapping_file_path = os.path.join('./data', 'fb2w.nt')  # Replace with your mapping file path
#
#         output_mapping_path = os.path.join(files_path, 'mapping_wikidata.tsv')
#         output_labels_path = os.path.join(files_path, 'label.tsv')
#         output_type_path = os.path.join(files_path, 'type.tsv')
#         output_type_mapping_path = os.path.join(files_path, 'type_mapping.tsv')
#         output_ontology_path = os.path.join(files_path, 'ontology.tsv')
#
#         main(files_path, mapping_file_path, output_mapping_path, output_labels_path,
#              output_type_path, output_type_mapping_path, output_ontology_path)


if __name__ == "__main__":
    dataset_name = "fb237"
    versions = [
        "v1",
        "v2",
        "v3",
        "v4",
    ]
    # mapping_file_path = ensure_file_exists()

    for version in versions:
        df_name = dataset_name + "_" + version
        df_name_ind = dataset_name + "_" + version + "_ind"
        files_path = os.path.abspath(os.path.join("./data", df_name))
        files_path_ind = os.path.abspath(os.path.join("./data", df_name_ind))

        print(f" Current Dataset {files_path} ")

        # check if the current dataset_directory_exists:
        if not os.path.exists(files_path) and not os.path.exists(files_path_ind):
            print(f" Dataset {files_path}  or {files_path_ind} not found.. \t SKIPPING")
            continue

        # output_type_mapping_path = os.path.join(files_path, 'type_mapping.tsv')
        ontology_path = os.path.join(files_path, "ontology.tsv")
        ontology_path_ind = os.path.join(files_path_ind, "ontology.tsv")
        ontology = merge_dataset(ontology_path, ontology_path_ind)
        ontology = ontology.dropna(thresh=3)

        train_onto, testval_onto = holdout_split(ontology, percentage=0.2)
        test_onto, val_onto = holdout_split(testval_onto, percentage=0.5)

        # Train ontology
        ontology_save_path = os.path.join(files_path, "onto.txt")
        train_onto = train_onto.applymap(
            lambda x: x.replace(" ", "_") if isinstance(x, str) else x
        )
        train_onto.to_csv(ontology_save_path, sep=" ", header=False, index=False)
        ontology_save_path_ind = os.path.join(files_path_ind, "onto.txt")
        train_onto.to_csv(ontology_save_path_ind, sep=" ", header=False, index=False)

        # Val ontology
        ontology_save_path = os.path.join(files_path, "onto_valid.txt")
        val_onto = val_onto.applymap(
            lambda x: x.replace(" ", "_") if isinstance(x, str) else x
        )

        val_onto.to_csv(ontology_save_path, sep=" ", header=False, index=False)
        ontology_save_path_ind = os.path.join(files_path_ind, "onto_valid.txt")
        val_onto.to_csv(ontology_save_path_ind, sep=" ", header=False, index=False)

        # Test ontology
        ontology_save_path = os.path.join(files_path, "onto_test.txt")
        test_onto = test_onto.applymap(
            lambda x: x.replace(" ", "_") if isinstance(x, str) else x
        )

        test_onto.to_csv(ontology_save_path, sep=" ", header=False, index=False)
        ontology_save_path_ind = os.path.join(files_path_ind, "onto_test.txt")
        test_onto.to_csv(ontology_save_path_ind, sep=" ", header=False, index=False)

        # Type saving
        files_names_type = [".txt", "_test.txt", "_valid.txt"]
        #  For vx
        type_path = os.path.join(files_path, "type.tsv")
        type_df = pd.read_csv(type_path, sep="\t", header=None)
        # For vx ind
        type_path_ind = os.path.join(files_path_ind, "type.tsv")
        type_df_ind = pd.read_csv(type_path_ind, sep="\t", header=None)
        for fnt in files_names_type:
            type_save_path = os.path.join(files_path, "type" + fnt)
            type_df = type_df.applymap(
                lambda x: x.replace(" ", "_") if isinstance(x, str) else x
            )

            type_df.to_csv(type_save_path, sep=" ", header=False, index=False)
            type_save_path = os.path.join(files_path_ind, "type" + fnt)
            type_df_ind = type_df_ind.applymap(
                lambda x: x.replace(" ", "_") if isinstance(x, str) else x
            )

            type_df_ind.to_csv(type_save_path, sep=" ", header=False, index=False)
