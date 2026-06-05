# Decisiones de arquitectura

## Fuente canónica

GBP es fuente canónica. Tienda Nube es destino de publicación.

## Precio

El precio se usa en importación inicial o actualización completa manual. No participa del ciclo frecuente.

## Stock

El stock es el único dato sincronizado con frecuencia para reducir riesgo de sobreventa.

## Módulo 16

Todo método GBP queda bloqueado por defecto. Se habilita solo con validación formal.

## Dominio independiente

El dominio no conoce SOAP, REST, XML, Tienda Nube ni nombres internos de GBP.
