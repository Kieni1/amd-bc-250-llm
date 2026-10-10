# bash completion for the supported bc250 multicall interface.
_bc250_complete() {
  local cur prev command
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]:-}"
  command="${COMP_WORDS[1]:-}"

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=( $(compgen -W 'agent-mode benchmark code code-commit compare-mtp doctor fetch-mtp gfx1013 gitea-review install maintenance model ocr ollama-profile openwebui-setup package-gate qualification rag reset resilience run-mtp status storage support-bundle verify version help --help --version' -- "$cur") )
    return 0
  fi

  case "$command" in
    gfx1013)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'status prepare enable disable reset benchmark help' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == benchmark && $COMP_CWORD -eq 3 ]]; then
        COMPREPLY=( $(compgen -W 'stock gfx restored status report' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == status ]]; then
        COMPREPLY=( $(compgen -W '--json' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" =~ ^(prepare|disable|reset)$ ]]; then
        COMPREPLY=( $(compgen -W '--check' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == benchmark && "${COMP_WORDS[3]:-}" == status ]]; then
        COMPREPLY=( $(compgen -W '--campaign-dir --json' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == benchmark && "${COMP_WORDS[3]:-}" == report ]]; then
        COMPREPLY=( $(compgen -W '--campaign-dir' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == benchmark ]]; then
        COMPREPLY=( $(compgen -W '--campaign-dir --include-deep --ollama-url --timeout --repeats --num-predict --telemetry-interval' -- "$cur") )
      fi
      ;;
    qualification)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'list clean' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == list ]]; then
        COMPREPLY=( $(compgen -W '--json' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == clean ]]; then
        COMPREPLY=( $(compgen -W '--older-than-days --keep-latest --apply' -- "$cur") )
      fi
      ;;
    version)
      COMPREPLY=( $(compgen -W '--json --short' -- "$cur") )
      ;;
    status|doctor)
      COMPREPLY=( $(compgen -W '--json' -- "$cur") )
      ;;
    benchmark)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'generation embeddings ocr task agent usecase translation rag-cycle rag-quality concurrency num-batch owui-translation owui-rag owui-embedding-batch owui-chunk-min owui-system-context' -- "$cur") )
      fi
      ;;
    package-gate)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'capture' -- "$cur") )
      fi
      ;;
    resilience)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'start resume status' -- "$cur") )
      fi
      ;;
  esac

  case "$prev" in
    --campaign-dir|--output|--output-dir|--candidate-rpm|--source-artifact|--token-file)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
}
complete -F _bc250_complete bc250
