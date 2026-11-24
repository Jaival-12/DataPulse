export type QualityDimension = 'completeness'|'validity'|'uniqueness'|'consistency'|'rule_based_correctness'
export type QualitySeverity = 'critical'|'high'|'medium'|'low'
export type QualityRule =
  | {type:'required_columns';columns:string[]}
  | {type:'not_null'|'unique'|'non_negative';column:string}
  | {type:'greater_than';column:string;value:number}
  | {type:'range';column:string;min_value:number;max_value:number}

export type DataQualityIssue = {
  id:string;report_id:string;dimension:QualityDimension;issue_type:string;severity:QualitySeverity
  column_name:string|null;affected_rows:number;affected_percentage:number;description:string
  sample_values:unknown[];recommendation:string
}

export type DataQualityReport = {
  id:string;dataset_id:string|null;processed_dataset_id:string|null;overall_score:number|null
  quality_label:string;dimension_scores:Record<QualityDimension,number|null>
  scoring_weights:Record<QualityDimension,number>;methodology:Record<string,unknown>;rules:QualityRule[]
  total_rows:number;total_columns:number;total_issues:number;status:'complete'|'not_scored';created_at:string
}

export type QualityReportPage={items:DataQualityReport[];total:number;limit:number;offset:number}
export type QualityIssuePage={items:DataQualityIssue[];total:number;limit:number;offset:number}
