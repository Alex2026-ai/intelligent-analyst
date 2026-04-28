import { useCallback, useRef, useState } from 'react';
import { Loader2, Upload, XCircle } from 'lucide-react';
import { UPLOAD_LIMITS } from '../constants';

export default function FileUploadZone({ onFileSelect, isProcessing, uploadProgress, uploadPhase, preflightError, fileInfo, limits }) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = useCallback((e) => { e.preventDefault(); e.stopPropagation(); }, []);
  const handleDragIn = useCallback((e) => { e.preventDefault(); e.stopPropagation(); if (!isProcessing) setIsDragging(true); }, [isProcessing]);
  const handleDragOut = useCallback((e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }, []);
  const handleDrop = useCallback((e) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    if (isProcessing) return;
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) onFileSelect(files[0]);
  }, [onFileSelect, isProcessing]);

  const handleFileInput = useCallback((e) => {
    if (isProcessing) return;
    const files = e.target.files;
    if (files && files.length > 0) {
      onFileSelect(files[0]);
      e.target.value = "";
    }
  }, [onFileSelect, isProcessing]);

  const handleClick = useCallback(() => {
    if (!isProcessing) fileInputRef.current?.click();
  }, [isProcessing]);

  const getStatusText = () => {
    if (uploadPhase === 'uploading') {
      return `Uploading... ${uploadProgress}%`;
    }
    if (uploadPhase === 'processing') {
      return 'Processing on server...';
    }
    return 'Drop your file here';
  };

  return (
    <div
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={handleClick}
      className={`
        border-2 border-dashed rounded-none p-12 text-center transition-all
        ${isDragging
          ? 'border-cyan-500 bg-cyan-500/10'
          : preflightError
            ? 'border-red-500/50 bg-red-500/5'
            : 'border-[#1e293b] hover:border-slate-500 bg-[#050b14]'
        }
        ${isProcessing ? 'cursor-wait' : 'cursor-pointer'}
      `}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx,.xls,.json,.txt,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
        onChange={handleFileInput}
        className="hidden"
        disabled={isProcessing}
      />
      {isProcessing ? (
        <Loader2 className="mx-auto text-cyan-500 animate-spin mb-4" size={48} />
      ) : preflightError ? (
        <XCircle className="mx-auto text-red-400 mb-4" size={48} />
      ) : (
        <Upload className="mx-auto text-gray-200 mb-4" size={48} />
      )}
      <p className="text-lg text-[#f1f5f9] font-semibold mb-2">
        {getStatusText()}
      </p>
      {isProcessing && (
        <div className="w-64 mx-auto bg-[#1e293b] rounded-full h-2 mb-4">
          <div
            className={`h-2 rounded-full transition-all duration-300 ${uploadPhase === 'processing' ? 'bg-amber-500 animate-pulse' : 'bg-cyan-500'}`}
            style={{ width: `${uploadPhase === 'processing' ? 100 : uploadProgress}%` }}
          />
        </div>
      )}
      {preflightError && !isProcessing && (
        <div className="max-w-md mx-auto mb-4">
          <div className="bg-red-500/10 border border-red-500/30 rounded p-3 text-left">
            <p className="text-red-400 text-sm font-semibold mb-1">Upload blocked</p>
            <p className="text-red-400/80 text-xs">{preflightError}</p>
            {fileInfo && (
              <div className="mt-2 pt-2 border-t border-red-500/20 text-[10px] text-gray-200 font-mono">
                <div>File: {fileInfo.name}</div>
                <div>Size: {(fileInfo.size / (1024 * 1024)).toFixed(2)} MB</div>
                {fileInfo.estimatedRows !== null && <div>Est. rows: ~{fileInfo.estimatedRows.toLocaleString()}</div>}
              </div>
            )}
          </div>
        </div>
      )}
      {!isProcessing && !preflightError && (
        <>
          <p className="text-sm text-[#cbd5e1] mb-2">
            or click to browse
          </p>
          <p className="text-xs text-[#94a3b8] mb-4">
            CSV, Excel (XLSX), JSON, or TXT
          </p>
          <p className="text-[10px] text-gray-200 font-mono uppercase tracking-widest">
            Max {limits?.maxUploadMb || UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB • Max {(limits?.maxRecordsPerBatch || UPLOAD_LIMITS.MAX_ROWS).toLocaleString()} records
          </p>
        </>
      )}
    </div>
  );
}
