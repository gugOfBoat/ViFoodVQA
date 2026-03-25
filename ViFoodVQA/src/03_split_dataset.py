import pandas as pd

df = pd.read_csv('vqa_rows.csv')

# print(df.columns)
columns_to_drop = [
    'is_checked', 'is_drop', 'created_at', 'updated_at',
    'q0_score', 'q1_score', 'q2_score', 'q3_score',
    'verify_decision', 'verify_rule', 'verify_notes'
]
# df = df.drop(columns=columns_to_drop)

# df_original = df.copy()

# display(df.head())

# display(df.columns)

import ast

df['text_len'] = df['question'].str.len() + \
                 df['choice_a'].str.len() + \
                 df['choice_b'].str.len() + \
                 df['choice_c'].str.len() + \
                 df['choice_d'].str.len()

display(df['text_len'])

def count_triples(item):
    if pd.isna(item):
        return 0
    if isinstance(item, str):
        try:
            evaluated_item = ast.literal_eval(item)
            if isinstance(evaluated_item, (list, tuple, set)):
                return len(evaluated_item)
            else:
                return 0
        except (ValueError, SyntaxError):
            return 0
    elif isinstance(item, (list, tuple, set)):
        return len(item)
    return 0

df['triplet_count'] = df['triples_used'].apply(count_triples)
display(df['triplet_count'])

# display(df.columns)

from sklearn.model_selection import StratifiedShuffleSplit
import numpy as np
import pandas as pd

# Assume 'df' already has 'text_len' and 'triplet_count' from previous cells

# 1. Create image_id-level stratification features
# Group by image_id and aggregate relevant features
image_level_features = df.groupby('image_id').agg(
    # Get the mode of qtype and triplet_count.
    # .mode() can return multiple values if there's a tie, so take the first one.
    qtype=('qtype', lambda x: x.mode()[0] if not x.mode().empty else np.nan),
    triplet_count=('triplet_count', lambda x: x.mode()[0] if not x.mode().empty else np.nan),
    # Get the mean of text_len for image_id
    text_len=('text_len', 'mean')
).reset_index()

# Drop rows with NaN values if mode was empty (shouldn't happen with valid data)
image_level_features.dropna(subset=['qtype', 'triplet_count'], inplace=True)

# 2. Bin 'text_len' for stratification at the image_id level
# Using pd.qcut on the image-level mean_text_len
image_level_features['text_len_binned'] = pd.qcut(
    image_level_features['text_len'],
    q=10,
    labels=False,
    duplicates='drop'
)

# 3. Combine features into a single stratification column for image_id
image_level_features['stratify_col'] = image_level_features['qtype'].astype(str) + '_' + \
                                       image_level_features['text_len_binned'].astype(str) + '_' + \
                                       image_level_features['triplet_count'].astype(str)

# 4. Handle potential small groups in stratification for image_df
min_samples_for_split = 2

stratify_counts_image = image_level_features['stratify_col'].value_counts()
too_small_groups_image = stratify_counts_image[stratify_counts_image < min_samples_for_split].index

if not too_small_groups_image.empty:
    valid_groups_image = stratify_counts_image[stratify_counts_image >= min_samples_for_split]
    if valid_groups_image.empty:
        raise ValueError("Cannot perform stratified split: all stratification groups in the image_level_features DataFrame are too small.")

    largest_group_name_image = valid_groups_image.idxmax()

    image_level_features.loc[
        image_level_features['stratify_col'].isin(too_small_groups_image),
        'stratify_col'
    ] = largest_group_name_image


# 5. Perform StratifiedShuffleSplit on unique image_ids
# Split into 70% for train, 30% for rest
sss1 = StratifiedShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
for train_index_img, temp_test_index_img in sss1.split(
    image_level_features, image_level_features['stratify_col']
):
    train_image_ids = image_level_features.iloc[train_index_img]['image_id']
    rest_image_features = image_level_features.iloc[temp_test_index_img].copy()

# Handle potential small groups in stratification for rest_image_features
stratify_counts_rest = rest_image_features['stratify_col'].value_counts()
too_small_groups_rest = stratify_counts_rest[stratify_counts_rest < min_samples_for_split].index

if not too_small_groups_rest.empty:
    valid_groups_rest = stratify_counts_rest[stratify_counts_rest >= min_samples_for_split]
    if valid_groups_rest.empty:
        raise ValueError("Cannot perform stratified split: all stratification groups in the rest_image_features DataFrame are too small.")

    largest_group_name_rest = valid_groups_rest.idxmax()

    rest_image_features.loc[
        rest_image_features['stratify_col'].isin(too_small_groups_rest),
        'stratify_col'
    ] = largest_group_name_rest

# Split 'rest_image_features' into 20% and 10% (from original 100%)
# This means splitting the 30% rest into 2/3 and 1/3 respectively.
# test_size = 10% / (20% + 10%) = 1/3
sss2 = StratifiedShuffleSplit(n_splits=1, test_size=1/3, random_state=42)
for test_index_img, validation_index_img in sss2.split(
    rest_image_features, rest_image_features['stratify_col']
):
    test_image_ids = rest_image_features.iloc[test_index_img]['image_id']
    validation_image_ids = rest_image_features.iloc[validation_index_img]['image_id']


# 6. Filter the original df using the split image_ids
df_70 = df[df['image_id'].isin(train_image_ids)]
df_20 = df[df['image_id'].isin(test_image_ids)]
df_10 = df[df['image_id'].isin(validation_image_ids)]

# Clean up temporary columns from the original df if they were added for temporary use
# (these columns are now created on `image_level_features` not `df`)
if 'text_len_binned' in df.columns:
    df = df.drop(columns=['text_len_binned'])
if 'stratify_col' in df.columns:
    df = df.drop(columns=['stratify_col'])


print(f"Shape of df_70: {df_70.shape}")
print(f"Shape of df_20: {df_20.shape}")
print(f"Shape of df_10: {df_10.shape}")

# Optional: Verify that image_ids are unique across splits
train_ids = set(df_70['image_id'].unique())
test_ids = set(df_20['image_id'].unique())
val_ids = set(df_10['image_id'].unique())

print(f"Intersection of train and test image_ids: {len(train_ids.intersection(test_ids))}")
print(f"Intersection of train and validation image_ids: {len(train_ids.intersection(val_ids))}")
print(f"Intersection of test and validation image_ids: {len(test_ids.intersection(val_ids))}")

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd # Ensure pandas is imported for DataFrame operations

dataframes = {'df': df, 'df_70': df_70, 'df_20': df_20, 'df_10': df_10}

# Determine custom_bins based on the original df for consistency across plots
max_text_len = df['text_len'].max()
custom_bins = np.arange(0, max_text_len + 50, 50)

# Get global order for qtype for consistent plotting
qtype_order = df['qtype'].value_counts().index

# Get global order for triplet_count for consistent plotting
triplet_count_order = df['triplet_count'].value_counts().index

# --- Create a single figure with a 3x4 grid for all plots ---
fig, axs = plt.subplots(3, 4, figsize=(20, 18), sharey='row') # Sharey across rows for better comparison of normalization

# Main title for the entire figure
fig.suptitle('Distribution Analysis Across Original and Split Dataframes', fontsize=20)

# Loop through dataframes and plot distributions
for i, (name, current_df) in enumerate(dataframes.items()):
    # Plotting qtype distributions (Row 0)
    qtype_percentages = current_df['qtype'].value_counts(normalize=True) * 100
    max_qtype_percentage = qtype_percentages.max() if qtype_percentages.size > 0 else 0
    if max_qtype_percentage > 0:
        normalized_qtype_percentages = qtype_percentages / max_qtype_percentage
    else:
        normalized_qtype_percentages = pd.Series(0.0, index=qtype_percentages.index)
    temp_df = pd.DataFrame({'qtype': normalized_qtype_percentages.index, 'normalized_percentage': normalized_qtype_percentages.values})
    sns.barplot(y='qtype', x='normalized_percentage', data=temp_df, order=qtype_order, ax=axs[0, i])
    axs[0, i].set_title(f'{name} - Qtype')
    axs[0, i].set_xlabel('Normalized Percentage')
    if i == 0:
        axs[0, i].set_ylabel('Question Type')
    else:
        axs[0, i].set_ylabel('')
    axs[0, i].set_xlim(0, 1) # Ensure normalized percentage axis goes from 0 to 1

    # Plotting text_len distributions (Row 1)
    counts, bins = np.histogram(current_df['text_len'], bins=custom_bins)
    max_count = counts.max() if counts.size > 0 else 0
    if max_count > 0:
        normalized_counts = counts / max_count
    else:
        normalized_counts = np.zeros_like(counts, dtype=float)
    axs[1, i].bar(bins[:-1], normalized_counts, width=np.diff(bins), align='edge', edgecolor='black')
    axs[1, i].set_title(f'{name} - Text Length')
    axs[1, i].set_xlabel('Text Length')
    if i == 0:
        axs[1, i].set_ylabel('Normalized Frequency')
    else:
        axs[1, i].set_ylabel('')
    axs[1, i].set_xticks(custom_bins[::2])
    axs[1, i].tick_params(axis='x', rotation=45)
    axs[1, i].set_ylim(0, 1.05) # Ensure y-axis covers the normalized range [0, 1]

    # Plotting triplet_count distributions (Row 2)
    triplet_value_counts = current_df['triplet_count'].value_counts()
    max_triplet_count = triplet_value_counts.max() if triplet_value_counts.size > 0 else 0
    if max_triplet_count > 0:
        normalized_triplet_value_counts = (triplet_value_counts / max_triplet_count).reset_index()
    else:
        normalized_triplet_value_counts = pd.DataFrame(columns=['triplet_count', 'count'])
    normalized_triplet_value_counts.columns = ['triplet_count', 'normalized_frequency']
    sns.barplot(x='triplet_count', y='normalized_frequency', data=normalized_triplet_value_counts, order=triplet_count_order, ax=axs[2, i])
    axs[2, i].set_title(f'{name} - Triplet Count')
    axs[2, i].set_xlabel('Number of Triplets Used')
    if i == 0:
        axs[2, i].set_ylabel('Normalized Count')
    else:
        axs[2, i].set_ylabel('')
    axs[2, i].set_ylim(0, 1.05) # Ensure y-axis covers the normalized range [0, 1]

plt.tight_layout(rect=[0, 0.03, 1, 0.98]) # Adjust rect to make space for suptitle
plt.savefig('distribution_analysis.png') # Save the combined figure
# plt.show()

columns_to_keep = [
    'vqa_id', 'image_id', 'qtype', 'question',
    'choice_a', 'choice_b', 'choice_c', 'choice_d',
    'answer', 'rationale', 'triples_used', 'is_checked',
    'is_drop', 'created_at', 'updated_at', 'q0_score',
    'q1_score', 'q2_score', 'q3_score', 'verify_decision',
    'verify_rule', 'verify_notes'
]

columns_to_keep = [
    'vqa_id'
]

# Filter dataframes to keep only specified columns
df_70_filtered = df_70[columns_to_keep].sort_values(by='vqa_id').reset_index(drop=True)
df_20_filtered = df_20[columns_to_keep].sort_values(by='vqa_id').reset_index(drop=True)
df_10_filtered = df_10[columns_to_keep].sort_values(by='vqa_id').reset_index(drop=True)

# Assign 'split' column
df_70_filtered['split'] = 'train'
df_20_filtered['split'] = 'test'
df_10_filtered['split'] = 'validate'

# Combine all filtered dataframes into one
vqa_processed_df = pd.concat([
    df_70_filtered,
    df_20_filtered,
    df_10_filtered
], ignore_index=True)
vqa_processed_df = vqa_processed_df.sort_values(by='vqa_id').reset_index(drop=True)

# Export to CSV
vqa_processed_df.to_csv('vqa_processed.csv', index=False)

print("Merged DataFrame exported successfully to vqa_processed.csv")

total_rows_df = len(df)
total_rows_splits = len(df_70) + len(df_20) + len(df_10)

print(f"Total rows in original df: {total_rows_df}")
print(f"Total rows in df_70 + df_20 + df_10: {total_rows_splits} ({len(df_70)} + {len(df_20)} + {len(df_10)})")

if total_rows_df == total_rows_splits:
    print("All rows are accounted for. No rows were lost during sampling.")
else:
    lost_rows = total_rows_df - total_rows_splits
    print(f"There was a discrepancy. {lost_rows} rows were lost or added during sampling.")

train_image_ids_set = set(df_70['image_id'].unique())
test_image_ids_set = set(df_20['image_id'].unique())
validation_image_ids_set = set(df_10['image_id'].unique())

# Calculate intersections
intersection_train_test = len(train_image_ids_set.intersection(test_image_ids_set))
intersection_train_validation = len(train_image_ids_set.intersection(validation_image_ids_set))
intersection_test_validation = len(test_image_ids_set.intersection(validation_image_ids_set))

# Print results
print(f"Number of overlapping image_ids between df_70 (train) and df_20 (test): {intersection_train_test}")
print(f"Number of overlapping image_ids between df_70 (train) and df_10 (validation): {intersection_train_validation}")
print(f"Number of overlapping image_ids between df_20 (test) and df_10 (validation): {intersection_test_validation}")

if intersection_train_test == 0 and intersection_train_validation == 0 and intersection_test_validation == 0:
    print("All image_ids are unique across the train, test, and validation splits.")
else:
    print("There are overlapping image_ids between the splits.")