import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react'
import type { DatasetColumn } from '../types/dataset'
import type { PipelineOperation, PipelineStepConfig } from '../types/pipeline'
import { operationNames, textOperations } from '../utils/pipelineBuilder'

type Props = {
  index: number
  operation: PipelineOperation
  config: PipelineStepConfig
  columns: DatasetColumn[]
  errors: string[]
  canMoveUp: boolean
  canMoveDown: boolean
  onChange: (operation: PipelineOperation, config: PipelineStepConfig) => void
  onMoveUp: () => void
  onMoveDown: () => void
  onRemove: () => void
}

const options = (columns: DatasetColumn[]) => columns.map(column => <option value={column.name} key={column.position}>{column.name}</option>)
function Field({label,children,hint}:{label:string;children:React.ReactNode;hint?:string}) {
  return <label className="builder-field"><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>
}
function MultiColumns({columns,value,onChange,label,hint}:{columns:DatasetColumn[];value:string[];onChange:(names:string[])=>void;label:string;hint?:string}) {
  return <fieldset className="builder-field multi-column-field"><legend>{label}</legend>{hint&&<small>{hint}</small>}
    <div className="builder-checkbox-list">{columns.map(column=><label key={column.name}><input type="checkbox" checked={value.includes(column.name)} onChange={event=>onChange(event.target.checked?[...value,column.name]:value.filter(name=>name!==column.name))}/><span>{column.name}</span><small>{column.data_type}</small></label>)}</div>
    {!columns.length&&<small>No columns are available at this step.</small>}
  </fieldset>
}

export function PipelineStepEditor({index,operation,config,columns,errors,canMoveUp,canMoveDown,onChange,onMoveUp,onMoveDown,onRemove}:Props) {
  const patch = (changes:PipelineStepConfig) => onChange(operation,{...config,...changes})
  const selected = (key:string) => (config[key] as string[] | undefined) ?? []
  const columnName = String(config.column ?? '')
  const selectedColumn = columns.find(column=>column.name===columnName)
  const updateTextOperation = (value:PipelineOperation) => onChange(value,config)
  const isTextOperation = textOperations.includes(operation)
  const renderOperand = (key:'left'|'right') => {
    const value = config[key]
    const isColumn = Boolean(value && typeof value==='object' && 'column' in value)
    const selectedValue = isColumn ? String((value as {column:string}).column) : String(value ?? '')
    return <div className="operand-editor" key={key}>
      <span className="operand-label">{key==='left'?'Left operand':'Right operand'}</span>
      <select aria-label={`${key} operand type`} value={isColumn?'column':'number'} onChange={event=>patch({[key]:event.target.value==='column'?{column:columns[0]?.name??''}:0})}>
        <option value="column">Column</option><option value="number">Number</option>
      </select>
      {isColumn?<select aria-label={`${key} operand column`} value={selectedValue} onChange={event=>patch({[key]:{column:event.target.value}})}>{options(columns)}</select>
        :<input aria-label={`${key} operand value`} type="number" step="any" value={selectedValue} onChange={event=>patch({[key]:event.target.value})} placeholder="0"/>}
    </div>
  }
  return <article className="step-card">
    <div className="step-card-heading"><div className="step-number"><GripVertical size={14}/><span>{String(index+1).padStart(2,'0')}</span></div><div className="step-title"><b>{operationNames[operation]}</b><small>{description(operation)}</small></div><div className="step-actions">
      <button type="button" title="Move step up" aria-label={`Move step ${index+1} up`} onClick={onMoveUp} disabled={!canMoveUp}><ArrowUp size={14}/></button>
      <button type="button" title="Move step down" aria-label={`Move step ${index+1} down`} onClick={onMoveDown} disabled={!canMoveDown}><ArrowDown size={14}/></button>
      <button type="button" className="step-remove" title="Remove step" aria-label={`Remove ${operationNames[operation]} step ${index+1}`} onClick={onRemove}><Trash2 size={14}/></button>
    </div></div>
    <div className="step-config">
      {operation==='remove_duplicates'&&<MultiColumns columns={columns} value={selected('subset')} onChange={subset=>patch({subset})} label="Match duplicates using" hint="Leave empty to compare all columns for exact duplicate rows."/>}
      {operation==='fill_missing'&&<>
        <Field label="Handling strategy"><select aria-label="Missing value strategy" value={String(config.strategy??'drop_rows')} onChange={event=>onChange(operation,event.target.value==='drop_rows'?{strategy:'drop_rows'}:{...config,strategy:event.target.value,columns:undefined})}><option value="drop_rows">Drop rows with missing values</option><option value="constant">Fill with a constant</option><option value="mean">Fill numeric column with mean</option><option value="median">Fill numeric column with median</option><option value="mode">Fill categorical column with mode</option></select></Field>
        {config.strategy==='drop_rows'?<MultiColumns columns={columns} value={selected('columns')} onChange={columnsValue=>patch({columns:columnsValue})} label="Limit to columns (optional)" hint="No selection drops rows with missing values anywhere."/>:<>
          <Field label="Column"><select aria-label="Missing value column" value={columnName} onChange={event=>patch({column:event.target.value})}>{options(columns)}</select></Field>
          {config.strategy==='constant'&&<Field label="Fill value"><input aria-label="Fill value" value={String(config.value??'')} onChange={event=>patch({value:event.target.value})} placeholder="Enter a value"/></Field>}
        </>}
      </>}
      {operation==='rename_columns'&&<div className="mapping-editor"><div className="mapping-heading"><b>Column mapping</b><button type="button" className="text-action" onClick={()=>{const mapping=(config.mapping??{}) as Record<string,string>;const available=columns.find(column=>!(column.name in mapping));if(available)patch({mapping:{...mapping,[available.name]:''}})}}><Plus size={13}/> Add mapping</button></div>{Object.entries((config.mapping??{}) as Record<string,string>).map(([oldName,newName])=><div className="mapping-row" key={oldName}><select aria-label="Column to rename" value={oldName} onChange={event=>{const mapping={...(config.mapping as Record<string,string>)};delete mapping[oldName];mapping[event.target.value]=newName;patch({mapping})}}>{options(columns)}</select><span>becomes</span><input aria-label={`New name for ${oldName}`} value={newName} onChange={event=>patch({mapping:{...(config.mapping as Record<string,string>),[oldName]:event.target.value}})} placeholder="New column name"/><button type="button" aria-label={`Remove mapping for ${oldName}`} onClick={()=>{const mapping={...(config.mapping as Record<string,string>)};delete mapping[oldName];patch({mapping})}}><Trash2 size={13}/></button></div>)}</div>}
      {operation==='remove_columns'&&<MultiColumns columns={columns} value={selected('columns')} onChange={columnsValue=>patch({columns:columnsValue})} label="Columns to remove" hint="At least one column must remain."/>}
      {operation==='reorder_columns'&&<div className="reorder-editor"><b>Output column order</b><small>Move each column into the desired order.</small>{selected('columns').map((name,position)=><div className="reorder-item" key={`${name}-${position}`}><span>{String(position+1).padStart(2,'0')}</span><b>{name}</b><div><button type="button" aria-label={`Move ${name} up`} onClick={()=>{if(position===0)return;const order=[...selected('columns')];[order[position-1],order[position]]=[order[position],order[position-1]];patch({columns:order})}} disabled={position===0}><ArrowUp size={13}/></button><button type="button" aria-label={`Move ${name} down`} onClick={()=>{const order=[...selected('columns')];if(position>=order.length-1)return;[order[position+1],order[position]]=[order[position],order[position+1]];patch({columns:order})}} disabled={position===selected('columns').length-1}><ArrowDown size={13}/></button></div></div>)}</div>}
      {operation==='filter_rows'&&<>
        <Field label="Column"><select aria-label="Filter column" value={columnName} onChange={event=>patch({column:event.target.value})}>{options(columns)}</select></Field>
        <Field label="Condition"><select aria-label="Filter operator" value={String(config.operator??'is_not_null')} onChange={event=>{const operator=event.target.value;const next:PipelineStepConfig={...config,operator};if(operator==='is_null'||operator==='is_not_null')delete next.value;patch(next)}}>
          <optgroup label="Value"><option value="equals">Equals</option><option value="not_equals">Does not equal</option><option value="contains">Contains</option><option value="not_contains">Does not contain</option></optgroup>
          <optgroup label="Numeric"><option value="greater_than">Greater than</option><option value="less_than">Less than</option><option value="greater_than_or_equal">Greater than or equal</option><option value="less_than_or_equal">Less than or equal</option></optgroup>
          <optgroup label="Missing values"><option value="is_null">Is missing</option><option value="is_not_null">Is not missing</option></optgroup>
        </select></Field>
        {!['is_null','is_not_null'].includes(String(config.operator))&&<Field label="Comparison value"><input aria-label="Filter value" type={['greater_than','less_than','greater_than_or_equal','less_than_or_equal'].includes(String(config.operator))?'number':'text'} step="any" value={String(config.value??'')} onChange={event=>patch({value:event.target.value})} placeholder={selectedColumn?.data_type==='integer'||selectedColumn?.data_type==='number'?'Enter a number':'Enter a value'}/></Field>}
      </>}
      {operation==='convert_type'&&<><Field label="Column"><select aria-label="Conversion column" value={columnName} onChange={event=>patch({column:event.target.value})}>{options(columns)}</select></Field><Field label="Convert to"><select aria-label="Target data type" value={String(config.target_type??'string')} onChange={event=>patch({target_type:event.target.value})}>{['string','integer','float','boolean','date'].map(type=><option key={type}>{type}</option>)}</select></Field></>}
      {isTextOperation&&<><Field label="Standardization"><select aria-label="Text standardization" value={operation} onChange={event=>updateTextOperation(event.target.value as PipelineOperation)}><option value="trim_whitespace">Trim whitespace</option><option value="lowercase">Lowercase</option><option value="uppercase">Uppercase</option><option value="title_case">Title case</option></select></Field><MultiColumns columns={columns} value={selected('columns')} onChange={columnsValue=>patch({columns:columnsValue})} label="Text columns"/></>}
      {operation==='add_calculated_column'&&<><Field label="New column name"><input aria-label="Calculated column name" value={String(config.name??'')} onChange={event=>patch({name:event.target.value})} placeholder="e.g. net_total"/></Field><div className="calculated-expression">{renderOperand('left')}<Field label="Arithmetic"><select aria-label="Arithmetic operator" value={String(config.operator??'add')} onChange={event=>patch({operator:event.target.value})}><option value="add">Add (+)</option><option value="subtract">Subtract (−)</option><option value="multiply">Multiply (×)</option><option value="divide">Divide (÷)</option></select></Field>{renderOperand('right')}</div><small className="safe-expression-note">Uses column references and numeric values only. No code is evaluated.</small></>}
      {errors.length>0&&<ul className="step-errors" aria-label={`Step ${index+1} validation errors`}>{errors.map(error=><li key={error}>{error}</li>)}</ul>}
    </div>
  </article>
}

function description(operation:PipelineOperation) {
  const descriptions:Record<PipelineOperation,string>={remove_duplicates:'Keep the first row for each duplicate group.',fill_missing:'Drop rows or fill empty values with a selected strategy.',rename_columns:'Change one or more column names.',remove_columns:'Remove selected fields from the output.',reorder_columns:'Choose the output order for all columns.',filter_rows:'Keep rows that match a condition.',convert_type:'Convert values and fail if any value is invalid.',trim_whitespace:'Normalize text values in selected columns.',lowercase:'Normalize text values in selected columns.',uppercase:'Normalize text values in selected columns.',title_case:'Normalize text values in selected columns.',add_calculated_column:'Create a value using safe arithmetic.'}
  return descriptions[operation]
}
