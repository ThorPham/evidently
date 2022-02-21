#!/usr/bin/env python
# coding: utf-8
from numbers import Number
from typing import Dict
from typing import Optional
from typing import Union

from dataclasses import dataclass, fields
import numpy as np
import pandas as pd

from evidently import ColumnMapping
from evidently.analyzers.base_analyzer import Analyzer
from evidently.analyzers.base_analyzer import BaseAnalyzerResult
from evidently.analyzers.utils import DatasetColumns
from evidently.analyzers.utils import process_columns


@dataclass
class FeaturesProfileStats:
    """Class for all features data profile metrics store.

    A type of the feature is stored in `feature_type` field.
    Concrete stat kit depends on the feature type. Is a metric is not applicable - leave `None` value for it.

    Metrics for all feature types:
        - feature type - cat for category, num for numeric, datetime for datetime features
        - count - quantity of a meaningful values (do not take into account NaN values)
        - missing_count - quantity of meaningless (NaN) values
        - missing_fraction - the proportion of the missed values
        - unique - quantity of unique values
        - unique_fraction - the proportion of the unique values
        - max - maximum value (not applicable for category features)
        - min - minimum value (not applicable for category features)
        - most_common_value - the most common value in the feature values
        - most_common_value_fraction - fraction of the most common value
        - most_common_not_null_value - if `most_common_value` equals NaN - the next most common value. Otherwise - None
        - most_common_not_null_value_fraction - fraction of `most_common_not_null_value` if it is defined.
            If `most_common_not_null_value` is not defined, equals None too.

    Metrics for numeric features only:
        - infinite_count - quantity infinite values (for numeric features only)
        - infinite_fraction - fraction of infinite values (for numeric features only)
        - percentile_25 - 25% percentile for meaningful values
        - percentile_50 - 50% percentile for meaningful values
        - percentile_75 - 75% percentile for meaningful values
        - mean - the sum of the meaningful values divided by the number of the meaningful values
        - std - standard deviation of the values

    Metrics for category features only:
        - new_in_current_values_count - quantity of new values in the current dataset after the reference
            Defined for reference dataset only.
        - new_in_current_values_count - quantity of values in the reference dataset that not presented in the current
            Defined for reference dataset only.
    """

    # feature type - cat for category, num for numeric, datetime for datetime features
    feature_type: str
    # quantity on
    count: int = 0
    infinite_count: Optional[int] = None
    infinite_fraction: Optional[float] = None
    missing_count: Optional[int] = None
    missing_fraction: Optional[float] = None
    unique: Optional[int] = None
    unique_fraction: Optional[float] = None
    percentile_25: Optional[float] = None
    percentile_50: Optional[float] = None
    percentile_75: Optional[float] = None
    max: Optional[Union[Number, str]] = None
    min: Optional[Union[Number, str]] = None
    mean: Optional[float] = None
    most_common_value: Optional[Union[Number, str]] = None
    most_common_value_fraction: Optional[float] = None
    std: Optional[float] = None
    most_common_not_null_value: Optional[Union[Number, str]] = None
    most_common_not_null_value_fraction: Optional[float] = None
    new_in_current_values_count: Optional[int] = None
    unused_in_current_values_count: Optional[int] = None

    def is_datetime(self):
        """Checks that the object store stats for a datetime feature"""
        return self.feature_type == "datetime"

    def is_numeric(self):
        """Checks that the object store stats for a numeric feature"""
        return self.feature_type == "num"

    def is_category(self):
        """Checks that the object store stats for a category feature"""
        return self.feature_type == "cat"

    def as_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(FeaturesProfileStats)}


@dataclass
class DataProfileStats:
    num_features_stats: Optional[Dict[str, FeaturesProfileStats]] = None
    cat_features_stats: Optional[Dict[str, FeaturesProfileStats]] = None
    datetime_features_stats: Optional[Dict[str, FeaturesProfileStats]] = None
    target_stats: Optional[Dict[str, FeaturesProfileStats]] = None

    def get_all_features(self) -> Dict[str, FeaturesProfileStats]:
        result = {}

        for features in (
            self.target_stats,
            self.datetime_features_stats,
            self.cat_features_stats,
            self.num_features_stats,
        ):
            if features is not None:
                result.update(features)

        return result

    def __getitem__(self, item) -> FeaturesProfileStats:
        for features in (
            self.target_stats,
            self.datetime_features_stats,
            self.cat_features_stats,
            self.num_features_stats,
        ):
            if features is not None and item in features:
                return features[item]

        raise KeyError(item)


@dataclass
class DataProfileAnalyzerResults(BaseAnalyzerResult):
    reference_features_stats: DataProfileStats
    current_features_stats: Optional[DataProfileStats] = None


class DataProfileAnalyzer(Analyzer):
    @staticmethod
    def get_results(analyzer_results) -> DataProfileAnalyzerResults:
        return analyzer_results[DataProfileAnalyzer]

    def _calculate_stats(self, dataset: pd.DataFrame, columns: DatasetColumns, task: Optional[str]) -> DataProfileStats:
        result = DataProfileStats()

        result.num_features_stats = {
            feature_name: self._get_features_stats(dataset[feature_name], feature_type="num")
            for feature_name in columns.num_feature_names
        }

        result.cat_features_stats = {
            feature_name: self._get_features_stats(dataset[feature_name], feature_type="cat")
            for feature_name in columns.cat_feature_names
        }

        if columns.utility_columns.date:
            date_list = columns.datetime_feature_names + [columns.utility_columns.date]

        else:
            date_list = columns.datetime_feature_names

        result.datetime_features_stats = {
            feature_name: self._get_features_stats(dataset[feature_name], feature_type="datetime")
            for feature_name in date_list
        }

        target_name = columns.utility_columns.target

        if target_name is not None and target_name in dataset:
            result.target_stats = {}
            if task == "classification":
                result.target_stats[target_name] = self._get_features_stats(dataset[target_name], feature_type="cat")

            else:
                result.target_stats[target_name] = self._get_features_stats(dataset[target_name], feature_type="num")

        return result

    def calculate(
        self,
        reference_data: pd.DataFrame,
        current_data: Optional[pd.DataFrame],
        column_mapping: ColumnMapping,
    ) -> DataProfileAnalyzerResults:
        columns = process_columns(reference_data, column_mapping)
        reference_features_stats = self._calculate_stats(reference_data, columns, column_mapping.task)

        current_features_stats: Optional[DataProfileStats]

        if current_data is not None:
            current_features_stats = self._calculate_stats(current_data, columns, column_mapping.task)

            if reference_features_stats.cat_features_stats is not None:
                # calculate additional stats of representation reference dataset values in the current dataset
                for feature_name in reference_features_stats.cat_features_stats:
                    cat_feature_stats = reference_features_stats.cat_features_stats[feature_name]
                    current_values_set = set(current_data[feature_name].unique())

                    if feature_name in reference_data:
                        reference_values_set = set(reference_data[feature_name].unique())

                    else:
                        reference_values_set = set()

                    new_in_current_values_count: int = len(current_values_set - reference_values_set)
                    unused_in_current_values_count = len(reference_values_set - current_values_set)

                    if current_data[feature_name].hasnans and reference_data[feature_name].hasnans:
                        new_in_current_values_count -= 1
                        unused_in_current_values_count -= 1

                    cat_feature_stats.new_in_current_values_count = new_in_current_values_count
                    cat_feature_stats.unused_in_current_values_count = unused_in_current_values_count

        else:
            current_features_stats = None

        results = DataProfileAnalyzerResults(
            columns=columns,
            reference_features_stats=reference_features_stats,
        )
        if current_features_stats is not None:
            results.current_features_stats = current_features_stats
        return results

    @staticmethod
    def _get_features_stats(feature: pd.Series, feature_type: str) -> FeaturesProfileStats:
        result = FeaturesProfileStats(feature_type=feature_type)
        all_values_count = feature.shape[0]

        if not all_values_count > 0:
            # we have no data, return default stats for en empty dataset
            return result

        common_stats = dict(feature.describe())

        result.missing_count = int(feature.isnull().sum())
        result.count = int(common_stats["count"])
        all_values_count = feature.shape[0]
        value_counts = feature.value_counts(dropna=False)

        if feature_type == "num":
            result.infinite_count = int(np.sum(np.isinf(feature)))
            result.infinite_fraction = np.round(result.infinite_count / all_values_count, 2)

        result.missing_fraction = np.round(result.missing_count / all_values_count, 2)

        if result.count > 0:
            result.most_common_value = value_counts.index[0]

            if feature_type == "datetime":
                # cast datatime value to str for datetime features
                result.most_common_value = str(result.most_common_value)

            result.most_common_value_fraction = np.round(value_counts.iloc[0] / all_values_count, 2)
            result.unique = feature.nunique()
            result.unique_fraction = np.round(result.unique / all_values_count, 2)

            if pd.isnull(result.most_common_value):
                result.most_common_not_null_value = value_counts.index[1]
                result.most_common_not_null_value_fraction = np.round(value_counts.iloc[1] / all_values_count, 2)

            if feature_type == "num":
                result.max = feature.max()
                result.min = feature.min()
                std = common_stats["std"]

                if np.isnan(std):
                    result.std = None

                else:
                    result.std = np.round(std, 2)

                result.mean = np.round(common_stats["mean"], 2)
                result.percentile_25 = np.round(common_stats["25%"], 2)
                result.percentile_50 = np.round(common_stats["50%"], 2)
                result.percentile_75 = np.round(common_stats["75%"], 2)

            if feature_type == "datetime":
                # cast datatime value to str for datetime features
                result.max = str(feature.max())
                result.min = str(feature.min())

        return result
