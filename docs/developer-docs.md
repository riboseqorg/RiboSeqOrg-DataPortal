# Developer Documentation

## Metadata Curation 
From a development perspective there are a number of key points to consider when understanding the workflow for the generation of high quality Ribo-Seq Metadata from the publicly available information. Firstly, a breakdown of the overall metadata curation process can be gleamed from the [core documentation](index.md). 

### Common Metadata Curation Pitfalls
The metadata curation process centred on the use of a standardised controlled vocabulary is prone to a number of common pitfalls. Here we document these and comment on how best to resolve them. It is expected that the release of new samples with unique metadata quirks will lead to the Data Portal development team coming up with new ways to patch these rules. However, knowing how we avoided issues in the past may help.

This is a ongoing process and new pitfalls may be identified. If so, add them below.

1. Insufficient Specificity
    The most common **mislabelling error** occurs where the alternative term that is stored in the controlled vocabulary for one term is a subset of unrelated metadata of a second valid term. An example of this was a Human sample that was labelled "Glioma Stem Cells" being mislabelled as coming from the Stem tissue. This occurs as 'Stem' as a term to identify samples taken from a plants stem cannot be made more specific without missing these samples. 

    The solution applied in this case was to create a more specific term for Glioma Stem Cells and position it within the controlled vocabulary above 'Stem'. This will result in these samples being labelled as Glioma and not Stem. 

2. Missing Field
    Another reason to lose information from the original metadata is that the required fields are not yet added to the RiboSeq.Org Controlled Vocabularies. This is relatively easy to fix. A field in this context is a column in the metadata table. If new metadata is downloaded and the workflow fails due to a field not existing in the Sample model in the Django app then we either need to merge the column into an existing field or create an entirely new field in the model. 

    For example, a new field is found in the metadata 'Time Since Infection'. This clearly has the same intended meaning as 'Time Post Infection' and as a result should be merged into the Timepoint column. However, as 'Time Since Infection' is not listed in the 'All Names' list for 'Timepoint' this will not be done automatically. To fix this, simply add the new term to the 'All Names' list for the suitable field and rerun the metadata processing. **Note:** it is best to fix all such conflicts in one go prior to re-running. 

    However, in the case where there is no obvious column to merge into it may be necessary to create a new field in the Sample model in the Django app. See Section on [Adding a Field](#add-field-to-metadata)

## Updating Metadata

To update metadata that is made publicly available on the RiboSeq Data Portal follow the following steps. 

The scripts and information pertaining to this process can be found in a [separate repository ](https://github.com/riboseqorg/Metadata). Here the logic behind these scripts are explained in more detail. To obtain a sample workflow of this data processing see [this](https://github.com/riboseqorg/Metadata/blob/main/workflow.md) document. 

### Add Field to Metadata 
Eventually it will be required to expand the number of fields used to describe the Ribo-Seq samples stored in the RDP database. Below are the simple steps required to add a field. 

1. Design The Field
    Identify a suitable name for the field. It will use minimal words to describe the column without ambiguity. The current convention is to name the column with the first letter capitalized, eg. 'Kit'. However, exceptions should be made where appropriate eg. 'rRNA Depletion'. 

2. Add the Django Model 
    This model will be found as the Sample Class in the `models.py` file. Using a local instance of the data portal simply append the new term as a property of the model. 
    Example:
    ```
    class Sample(models.Model):
    ...
        Kit = models.CharField(max_length=200, blank=True)
    ...
    ```
    Following this, a migration of the database needs to be carried out. In the app directory (`RiboSeqOrg-DataPortal/riboseqorg`) run: 
    ```
    python manage.py makemigrations
    ```
    You are then encouraged to 'check' the migrations. But I often skip this step although I know it is bad practice. 

    Then apply the migration:
    ``` 
    python manage.py migrate 
    ```

3. Load the data
    You should now be able to load the data using fixtures with the `json` file containing this field. 




## Creating Versions

Creating versions for resources in RDP is a crucial step for tracking changes. Here's how you can create versions:

1. Use the version control system supported by RDP.
2. Tag your repository with the desired version number.
3. Ensure that documentation reflects the changes made in the new version.

## Advanced Topics

Explore advanced topics related to development in RDP:

- **Customization**: Learn how to customize the behavior of RDP tools to fit your requirements.
- **Integration**: Integrate RDP with other tools and services.
- **Contributing**: Contribute to the development of RDP by following the contribution guidelines.

For more detailed information, refer to the specific documentation for each advanced topic.
