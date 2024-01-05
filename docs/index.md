# Welcome to RDP-Docs's Documentation!

## Table of Contents

- [Introduction](#introduction)
- [Data Portal Functionality](#data-portal-functionality)
- [Metadata Curation](#metadata-curation)
- [Developer Documentation](developer-docs.md)
  - [Updating Metadata](developer-docs.md#updating-metadata)
  - [Creating Versions](developer-docs.md#creating-versions)
- [Additional Resources](#additional-resources)

## Introduction

This documentation covers both the information relevant to a user of the Data Portal as well as that of interest to a RDP developer. Firstly, we break down the functionality available via the data portal and then we break down how the metadata curation process works. 

## Data Portal Functionality 

The RiboSeq Data Portal provides the following functionality for the exploration of existing Ribo-Seq datasets. Follow the links to view the in-depth explanations
 - [Sample and Study Exploration ](portal.md#exploration)
 - [Sample Search and Filtering based on Metadata](portal.md#search-and-filter)
 - [File Downloads](portal.md#file-download)
 - [Quality Control reports ](portal.md#data-quality-control)
 - [Visualise Data on RiboSeq.Org Resources](portal.md#visualise-and-analyse)
 - [REST API & RDP-Tools ](portal.md#rest-api-and-rdp-tools)

## Metadata Curation

The curate metadata presented through the data portal the following steps must be carried out. This is a general overview similar to what is provided in the manuscript. If you are a developer of the Data Portal then please see the [Developer Documentation](developer-docs.md)

#### 1. Find Relevant Studies
A search is carried out against the BioProjects database using the [ORFik](https://github.com/Roleren/ORFik) function `get_bioproject_candidates()` using the following search phrase:
```
(Ribosomal footprinting) OR (Ribosome footprinting) OR (Ribosome profiling) OR ribo-seq
```
This could of course be altered to identify a wider net of studies but this is a conservative approach that results in a higher proportion of Ribo-Seq studies. 

#### 2. Fetch Raw Metadata 
Raw metadata is obtained for each of these candidate studies via the Sequence Read Archives Run Info Tables. This Metadata contains a set of 'Core Columns' that are shared across all samples regardless of who uploaded them. This contains basic information such as related accessions and the number of reads (spots) in the sample.

Oftentimes this metadata will also include 'Open Columns' that are manually added by the data submitter. These Variable or Open columns are not standardised b SRA and whether they match between studies will depend entirely on the nomenclature and spelling used by the data submitter. These columns are typically essential for understanding the contents of a sequencing run. 

#### 3. Filter for Ribo-Seq Runs (Samples)
Based on the sample specific metadata we then make a call as to whether the sample contains ribosome protected fragments or not. Prior to this stage we assume that we have identified Ribo-Seq containing studies. However, it is increasingly common for these studies to contain multiple different data types. Most commonly RNA-Seq. This steps aims to identify the Ribo-Seq from the Other-Seq. The paired RNA-Seq is of course of relevance to Ribo-Seq analysis but for now this is not considered to be within the remit of the RiboSeq Data Portal. 

A sample is deemed to contain Ribo-Seq if `Run`, `LibraryName` or `sample_title` contains any of the following terms:
```
"ribo", "footprint", "RPF", "RFP", "80S", "MNAse", "translatome"
```
These are high confidence terms that are unlikely to lead to contamination of the dataset with non-Ribo-Seq samples. However, this will not catch all Ribo-Seq samples. To attempt to catch missed samples we also search with the following, as well as the use of a whitelist of samples or studies that we know should be included: 
```
"rp", "rf", "fp"
```

#### 4. Standardise Field Names
Once we have obtained a set of Ribo-Seq samples and their associated metadata the next step is to ensure that all fields (columns) in the metadata table that contain the same kind of information, for example those that refer to the inhibitor used, are merged into the one column with a standardised sensible field name. To this end we have developed a set of controlled vocabularies where synonymous terms (we call them 'All names') are recorded and where these are found in the column name of a studies metadata that column is merged into a column under the 'Main Name' for that term. 

This controlled vocabulary that is used to update terms is iteratively updated to accommodate the metadata that we encounter when new Ribo-Seq studies are identified. 

#### 5. Standardise Field Values
The next step is to ensure that all values within each field that refer to the sample thing are standardised to use one clear term. For example, 'Cyclohex', 'Cyclohexamide' and 'Cycloheximide' all refer to the same inhibitor. This is carried out in a similar process where a list of 'All Names' is maintained and where matches occur with a value the matching term is updated to take on the 'Main Name'. This greatly simplifies the diversity of values across columns. 

These controlled vocabularies were developed on the back of original work prior to the inception of RDP and as a result some choices were made that are sub optimal. As the RDP develops we aim to lean more heavily on published ontologies to ensure that the controlled vocabularies are populated with sensible synonyms. 

#### 6. Preparation for Loading 
Once the fields and values are standardised and all of the metadata is stored in a large csv file we can begin to prepare this data and fetch further study-level metadata in order to populate the Data Portal. NCBI APIs are used to obtain relevant information about each project including publication info and further protocol details that are not provided at sample level. 

Cleaned metadata and study-level metadata is formatted into fixtures in JSON format and loaded into a local version of the RDP database (SQLite). A pull request is then made against the `main` branch of the repository. This is where the production version of the app is found. This version should run on anyones local machine with the latest functionality. The `live` branch contains the actual version running on the production server with slight configuration changes for interaction with Apache. 

## Developer Documentation

Welcome to the developer documentation for RDP. This section provides detailed information on updating metadata, creating versions of the resource, and more.

### [Updating Metadata](developer-docs.md#updating-metadata)

Learn how to update metadata for resources in RDP.

### [Creating Versions](developer-docs.md#creating-versions)

Understand the process of creating versions for resources.

### Advanced Topics

Explore advanced topics related to development in RDP.

## Additional Resources

Find additional resources and links for further information.
